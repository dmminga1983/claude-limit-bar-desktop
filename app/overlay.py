"""Вариант 2: мини-окошко поверх экрана (always-on-top), которое можно
перетащить мышью. Единственный поток Tk запускается один раз при старте и
живёт всё время; «включить/выключить» — это показать/спрятать окно. Все
обращения к Tk из других потоков идут через флаги под замком, а сам Tk-поток
раз в 300 мс их забирает (напрямую из чужих потоков Tk трогать нельзя).

Внешний вид — «стеклянная» карточка: окно само становится цветовым ключом
(-transparentcolor), так что фон виден насквозь без закрашенной подложки.
Раньше здесь ещё пытались включить настоящее размытие фона через
недокументированный DWM-вызов SetWindowCompositionAttribute с
ACCENT_ENABLE_ACRYLICBLURBEHIND — убрано: на практике этот вызов в сочетании
с -transparentcolor ломает перерисовку окна у DWM (композитор застревает на
статичной «призрачной» подложке с одним только заголовком вместо живого
содержимого, хотя сам процесс и Tk-поток работают нормально) — подтверждено
прямым сравнением захвата экрана с включённым и выключенным блюром.
"""
import ctypes
import logging
import sys
import threading
import tkinter as tk
from typing import Any, Callable, Dict, Optional

from . import foreground, model

log = logging.getLogger("claude_limit_bar")

MODE_ALWAYS = "always"
MODE_CLAUDE_ONLY = "claude_only"
FOREGROUND_POLL_TICKS = 2  # проверяем активное окно раз в TICK_MS * 2 (~600 мс) — дешевле, чем каждый тик

# Тёмная стеклянная тема (используется и как тонировка настоящего блюра, и
# как фон нарисованной карточки в fallback-режиме).
GLASS_RGB = (0x1b, 0x1d, 0x23)
BG = "#{:02x}{:02x}{:02x}".format(*GLASS_RGB)
BORDER = "#3a3d46"      # тонкая светлая обводка стекла
HIGHLIGHT = "#4a4e59"   # блик по верхнему краю карточки
TRACK = "#2e3038"       # фон дорожки шкалы
TEXT = "#f2f2f3"        # светлая подпись процента — пока заливка до неё не дошла
TEXT_DARK = "#15171c"   # тёмная подпись процента — когда она уже "едет" по заливке
MUTED = "#9a9da5"

# Компактная карточка: ширина фиксирована (сужена по просьбе пользователя —
# кнопки "бесплатный сброс" больше нет, место под неё не нужно), высота
# подгоняется под содержимое (model.content_height). Сами высоты строк — в
# model.py (LAYOUT_*), чтобы их можно было проверить тестами без tkinter;
# здесь — только то, что относится к рисованию. H_PAD — горизонтальный
# отступ карточки (независим от вертикального PAD из model.LAYOUT_PAD).
H_PAD = 6        # горизонтальный отступ карточки слева/справа
LABEL_W = 15     # место под подпись "5ч" / "нед"
WIDTH = 92
RADIUS = 11
PAD = model.LAYOUT_PAD
BAR_X = H_PAD + LABEL_W
BAR_W = WIDTH - BAR_X - H_PAD
BAR_H = model.LAYOUT_BAR_H
ROW_GAP = model.LAYOUT_ROW_GAP
RESET_H = model.LAYOUT_RESET_H
NO_DATA_H = model.LAYOUT_NO_DATA_H

FONT_LABEL = ("Segoe UI", 7)
FONT_PCT = ("Segoe UI", 7, "bold")
FONT_RESET = ("Segoe UI", 6)

TICK_MS = 300
SNAP_MARGIN = 24  # px: если отпустили окошко ближе этого расстояния к краю/углу экрана — прилипает


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """Скруглённый прямоугольник на Canvas (tkinter не умеет его напрямую) —
    полигон с гладкой (smooth) интерполяцией через точки у углов."""
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def _effective_visible(want: bool, mode: str, claude_foreground: bool) -> bool:
    """Чистая логика решения, должно ли окошко сейчас реально быть видимым:
    в режиме MODE_ALWAYS — как захотели (want); в MODE_CLAUDE_ONLY —
    дополнительно только пока активно окно/вкладка Claude. Вынесено отдельно
    от _tick, чтобы проверять тестами без реального окна Tk."""
    if mode == MODE_CLAUDE_ONLY:
        return bool(want) and bool(claude_foreground)
    return bool(want)


def _lighten(hex_color: str, amount: float) -> str:
    """Осветляет цвет в сторону белого на `amount` (0..1) — для лёгкого
    глянцевого блика поверх залитой части шкалы."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    r = round(r + (255 - r) * amount)
    g = round(g + (255 - g) * amount)
    b = round(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _resolve_toplevel_hwnd(tk_hwnd: int) -> int:
    """tkinter.winfo_id() на Windows возвращает HWND ВНУТРЕННЕГО дочернего
    окна (клиентской области Tk), а не настоящего верхнего окна-обёртки,
    которое Windows считает top-level — SetWindowPos на нём двигает только
    внутренний виджет, а не само окно. GetParent() поднимает нас к реальной
    обёртке. Используется для быстрого перетаскивания и самовосстановления
    позиции — поэтому считается один раз и кладётся в self._hwnd, а не на
    каждый вызов."""
    if sys.platform != "win32":
        return tk_hwnd
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        get_parent = user32.GetParent
        get_parent.restype = ctypes.c_void_p
        get_parent.argtypes = [ctypes.c_void_p]
        parent = get_parent(ctypes.c_void_p(tk_hwnd))
        return int(parent) if parent else tk_hwnd
    except Exception:
        log.error("overlay: GetParent lookup failed:\n%s", __import__("traceback").format_exc())
        return tk_hwnd


class OverlayWidget:
    def __init__(
        self,
        config,
        on_hide: Callable[[], None],
        is_tray_enabled: Callable[[], bool],
        on_toggle_tray: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self.config = config
        self._on_hide = on_hide
        self._is_tray_enabled = is_tray_enabled
        self._on_toggle_tray = on_toggle_tray
        self._on_quit = on_quit

        self.root: Optional[tk.Tk] = None
        self.canvas: Optional[tk.Canvas] = None
        self._lock = threading.Lock()
        self._data: Optional[Dict[str, Any]] = None
        self._free_reset = False
        self._dirty = True
        self._want_visible = False
        self._shown: Optional[bool] = None
        self._drag = {"x": 0, "y": 0}
        self._tray_var: Optional[tk.BooleanVar] = None
        self._transparent = False  # удалось ли сделать само окно без сплошной подложки
        self._hwnd: Optional[int] = None  # настоящий top-level HWND (Windows) — считается один раз в _build
        self._x: Optional[int] = None  # последняя известная (нужная) позиция окна — самовосстанавливается
        self._y: Optional[int] = None  # каждый тик в _tick, см. комментарий там
        self._dragging = False  # True между ButtonPress-1 и ButtonRelease-1 — не мешаем активному перетаскиванию
        self._height = NO_DATA_H + PAD * 2  # текущая высота окна; подгоняется в _redraw под содержимое
        self._mode = str(config.get("overlay_mode") or MODE_ALWAYS) if config else MODE_ALWAYS
        self._mode_var: Optional[tk.StringVar] = None
        self._claude_foreground = True  # пока не проверили ни разу — не прячем окно сразу
        self._tick_count = 0

    # ---- потокобезопасный интерфейс (зовётся из любых потоков) -------------
    def update(self, data: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            self._data = data
            self._dirty = True

    def set_free_reset(self, available: bool) -> None:
        with self._lock:
            if self._free_reset != bool(available):
                self._free_reset = bool(available)
                self._dirty = True

    def set_visible(self, visible: bool) -> None:
        with self._lock:
            self._want_visible = bool(visible)

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode

    # ---- Tk-поток ---------------------------------------------------------
    def run(self) -> None:
        """Запускать ОДИН раз в отдельном потоке: он владеет циклом Tk."""
        self._build()
        self._tick()
        self.root.mainloop()

    def _build(self) -> None:
        self.root = tk.Tk()
        self.root.title("Claude — лимит")
        self.root.overrideredirect(True)  # без рамки и заголовка
        self.root.attributes("-topmost", True)
        # overrideredirect САМ ПО СЕБЕ не убирает кнопку окна с панели задач
        # Windows — для этого нужен явный WS_EX_TOOLWINDOW через "-toolwindow".
        # Без него рядом с системным треем на панели задач висит ещё и
        # отдельная кнопка самого окошка.
        try:
            self.root.attributes("-toolwindow", True)
        except tk.TclError:
            pass

        x, y = self.config.get("overlay_x"), self.config.get("overlay_y")
        if x is None or y is None:
            x, y = self.root.winfo_screenwidth() - WIDTH - 24, 24
        self._x, self._y = int(x), int(y)
        self.root.geometry(f"{WIDTH}x{self._height}+{int(x)}+{int(y)}")
        self.root.configure(bg=BG)
        self.root.deiconify()
        self.root.update_idletasks()  # нужен реальный HWND до дальнейшей настройки

        try:
            self._hwnd = _resolve_toplevel_hwnd(self.root.winfo_id())
        except Exception:
            log.error("overlay: hwnd resolve crashed:\n%s", __import__("traceback").format_exc())

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=self._height, bg=BG, highlightthickness=0)
        # Серая карточка-подложка вокруг шкал убрана по просьбе пользователя:
        # само окно делаем цветовым ключом (-transparentcolor), тогда всё,
        # что осталось цвета BG, становится по-настоящему прозрачным — видно
        # рабочий стол насквозь, а не закрашенный тёмный прямоугольник.
        try:
            self.root.attributes("-transparentcolor", BG)
            self._transparent = True
        except tk.TclError:
            log.error("overlay: -transparentcolor not supported, falling back:\n%s", __import__("traceback").format_exc())
            self._transparent = False
            # На платформах без настоящей прозрачности окна — лучшее, что
            # можем: обычная полупрозрачность окна (и рисуем закрытую
            # карточку сами, см. _redraw).
            try:
                self.root.attributes("-alpha", 0.94)
            except tk.TclError:
                pass

        self.root.withdraw()  # покажет _tick, когда set_visible(True)

        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._do_drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<ButtonPress-3>", self._popup_menu)

        self._tray_var = tk.BooleanVar(value=bool(self._is_tray_enabled()))
        self._mode_var = tk.StringVar(value=self._mode)
        self._menu = tk.Menu(self.root, tearoff=0)
        self._menu.add_command(label="Скрыть окошко", command=self._on_hide)
        self._menu.add_checkbutton(
            label="Значок в трее", variable=self._tray_var, command=self._on_toggle_tray
        )
        self._menu.add_separator()
        mode_menu = tk.Menu(self._menu, tearoff=0)
        mode_menu.add_radiobutton(
            label="Поверх всех окон",
            variable=self._mode_var, value=MODE_ALWAYS,
            command=lambda: self._set_mode(MODE_ALWAYS),
        )
        mode_menu.add_radiobutton(
            label="Только при использовании Claude",
            variable=self._mode_var, value=MODE_CLAUDE_ONLY,
            command=lambda: self._set_mode(MODE_CLAUDE_ONLY),
        )
        self._menu.add_cascade(label="Показывать", menu=mode_menu)
        self._menu.add_separator()
        self._menu.add_command(label="Выход", command=self._on_quit)
        self.root.protocol("WM_DELETE_WINDOW", self._on_hide)

    def _set_mode(self, mode: str) -> None:
        self.set_mode(mode)
        if self.config is not None:
            self.config.set("overlay_mode", mode)

    def _tick(self) -> None:
        with self._lock:
            want, dirty, mode = self._want_visible, self._dirty, self._mode
            self._dirty = False

        if mode == MODE_CLAUDE_ONLY:
            self._tick_count += 1
            # Проверяем активное окно не каждый тик (300 мс), а реже — это
            # обращение к WinAPI, незачем делать это так часто.
            if self._tick_count % FOREGROUND_POLL_TICKS == 0:
                self._claude_foreground = foreground.claude_is_foreground()

        effective_want = _effective_visible(want, mode, self._claude_foreground)

        if effective_want != self._shown:
            self._shown = effective_want
            if effective_want:
                self.root.deiconify()
                self.root.attributes("-topmost", True)
            else:
                self.root.withdraw()
        if self._shown and not self._dragging and self._x is not None and self._y is not None:
            # На Windows overrideredirect+layered окно изредка само "уезжает"
            # с заданного места — вплоть до того, что Windows сворачивает его
            # в иконическое состояние (HWND оказывается на служебной позиции
            # вроде (-32000,-32000), как у обычных свёрнутых окон), хотя сам
            # Tk-поток и не думал вызывать iconify(). Конкретный триггер
            # неясен, но эффект воспроизводится в реальном приложении —
            # поэтому каждый тик самовосстанавливаем и состояние, и позицию,
            # а не полагаемся на кэш Tk (winfo_x()/winfo_y()/state()), который
            # может не знать о таком внешнем сдвиге.
            self._restore_if_minimized()
            self._move_window(self._x, self._y)
            # "Поверх всех окон" на Windows — это не разовая установка
            # флага, а место в общей очереди topmost-окон: кто последним
            # попросил HWND_TOPMOST, тот и наверху. Полноэкранное окно
            # (например, Claude в полноэкранном режиме) при входе в
            # полноэкранный режим обычно само просит topmost и перебивает
            # нас. Поэтому каждый тик отвоёвываем верх заново — дёшево и не
            # мигает, если мы и так уже наверху.
            self._reassert_topmost()
        if dirty:
            self._redraw()
        self.root.after(TICK_MS, self._tick)

    def _popup_menu(self, event) -> None:
        self._tray_var.set(bool(self._is_tray_enabled()))
        with self._lock:
            self._mode_var.set(self._mode)
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _restore_if_minimized(self) -> None:
        """Если окно оказалось в иконическом (свёрнутом) состоянии — которое
        мы сами никогда не запрашиваем, но которое на практике иногда
        выставляется извне, — снимаем его через ShowWindow(SW_RESTORE).
        SetWindowPos сам по себе не снимает иконическое состояние, поэтому
        без этого самовосстановление позиции в _tick не сработало бы."""
        if sys.platform != "win32" or not self._hwnd:
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            if user32.IsIconic(ctypes.c_void_p(self._hwnd)):
                SW_RESTORE = 9
                user32.ShowWindow(ctypes.c_void_p(self._hwnd), SW_RESTORE)
        except Exception:
            log.error("overlay: restore-if-minimized failed:\n%s", __import__("traceback").format_exc())

    def _reassert_topmost(self) -> None:
        """Явно просит ОС снова поставить нас в начало очереди
        topmost-окон (HWND_TOPMOST), а не полагается на то, что
        Tk-атрибут "-topmost" уже когда-то был выставлен: другое
        topmost-окно (например, Claude, переходящий в полноэкранный режим)
        могло попросить то же самое позже нас и встать поверх."""
        if sys.platform != "win32" or not self._hwnd:
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            HWND_TOPMOST = ctypes.c_void_p(-1)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(
                ctypes.c_void_p(self._hwnd), HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:
            log.error("overlay: reassert-topmost failed:\n%s", __import__("traceback").format_exc())

    # ---- перетаскивание ----------------------------------------------------
    def _move_window(self, x: int, y: int) -> None:
        """Передвигает окно в (x, y). На Windows — напрямую через WinAPI
        SetWindowPos по уже закэшированному self._hwnd: это прямой вызов
        ОС без похода через Tcl-интерпретатор (`wm geometry` каждый раз
        заново парсит и форматирует строку геометрии "+x+y" и к тому же на
        каждый вызов заново считает layout — на частых событиях движения
        мыши это и давало заметное отставание окна от курсора). SWP_NOSIZE
        и SWP_NOZORDER — трогаем только позицию, ничего больше пересчитывать
        не нужно. На не-Windows (или если hwnd ещё не определился) —
        обычный путь через Tk."""
        if sys.platform == "win32" and self._hwnd:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010
                SWP_NOSIZE = 0x0001
                user32.SetWindowPos(
                    ctypes.c_void_p(self._hwnd), None, int(x), int(y), 0, 0,
                    SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOSIZE,
                )
                return
            except Exception:
                log.error("overlay: SetWindowPos failed, falling back to wm geometry:\n%s", __import__("traceback").format_exc())
        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _start_drag(self, event) -> None:
        # Запоминаем смещение курсора ОТНОСИТЕЛЬНО экрана (x_root/y_root), а
        # не координаты внутри окна: winfo_x()/winfo_y() — это запрос к
        # оконному менеджеру, и его достаточно сделать один раз при нажатии,
        # а не на каждое движение мыши в _do_drag.
        self._dragging = True
        self._drag = {
            "x": event.x_root - self.root.winfo_x(),
            "y": event.y_root - self.root.winfo_y(),
        }

    def _do_drag(self, event) -> None:
        x = event.x_root - self._drag["x"]
        y = event.y_root - self._drag["y"]
        self._x, self._y = x, y
        self._move_window(x, y)

    def _end_drag(self, event) -> None:
        x, y = self._snap(self.root.winfo_x(), self.root.winfo_y())
        self._move_window(x, y)
        self._x, self._y = x, y
        self._dragging = False
        self.config.set("overlay_x", x)
        self.config.set("overlay_y", y)

    def _snap(self, x: int, y: int) -> tuple:
        """Притягивает окошко к ближайшему краю/углу экрана, если оно было
        отпущено рядом (в пределах SNAP_MARGIN пикселей)."""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if x <= SNAP_MARGIN:
            x = 0
        elif x + WIDTH >= sw - SNAP_MARGIN:
            x = sw - WIDTH
        if y <= SNAP_MARGIN:
            y = 0
        elif y + self._height >= sh - SNAP_MARGIN:
            y = sh - self._height
        return x, y

    # ---- отрисовка ----------------------------------------------------------
    def _resize_to(self, height: int) -> None:
        """Подгоняет высоту окна и канваса под содержимое (ширина не
        меняется). Зовётся только когда высота реально изменилась — не на
        каждую перерисовку."""
        if height == self._height:
            return
        self._height = height
        self.canvas.configure(height=height)
        # Только размер, без позиции — Tk сохранит текущие x/y окна.
        self.root.geometry(f"{WIDTH}x{height}")

    def _redraw(self) -> None:
        with self._lock:
            data = self._data
        ws = model.windows_from_data(data)[:2]
        # Кнопка "бесплатный сброс" убрана по просьбе пользователя — высота
        # больше от неё не зависит.
        self._resize_to(model.content_height(ws, False))

        c = self.canvas
        c.delete("all")

        if self._transparent:
            # Всё, что цвета BG, окно само сделало прозрачным (-transparentcolor)
            # — не закрашиваем фон, только тонкая обводка-«стекло» по контуру.
            _round_rect(c, 1, 1, WIDTH - 1, self._height - 1, RADIUS, outline=BORDER, width=1, fill="")
        else:
            # Платформа без настоящей прозрачности окна — рисуем карточку сами.
            _round_rect(c, 0, 0, WIDTH, self._height, RADIUS, fill=BG, outline=BORDER, width=1)
            _round_rect(c, 2, 2, WIDTH - 2, self._height * 0.3, RADIUS - 2, fill=HIGHLIGHT, outline="", stipple="gray25")

        if not ws:
            c.create_text(H_PAD, self._height / 2, anchor="w", text="Claude · нет данных", fill=MUTED, font=FONT_LABEL)
            return

        y = PAD
        for win in ws:
            label = model.LABELS[win["key"]][0]
            c.create_text(H_PAD, y + BAR_H / 2, anchor="w", text=label, fill=MUTED, font=FONT_LABEL)
            _round_rect(c, BAR_X, y, BAR_X + BAR_W, y + BAR_H, BAR_H / 2, fill=TRACK, outline="")
            fill_w = model.fill_width(BAR_W, win["used"], BAR_H)
            color = model.color_for(win["used"])
            if fill_w > 0:
                _round_rect(c, BAR_X, y, BAR_X + fill_w, y + BAR_H, BAR_H / 2, fill=color, outline="")
                # лёгкий глянцевый блик на верхней половине залитой части шкалы
                if fill_w > 2:
                    _round_rect(
                        c, BAR_X + 1, y + 1, BAR_X + fill_w - 1, y + BAR_H * 0.5, (BAR_H / 2) - 1,
                        fill=_lighten(color, 0.35), outline="", stipple="gray50",
                    )

            # Подпись процента по умолчанию прижата к правому краю (светлая —
            # там тёмная дорожка). Когда заливка подбирается близко, подпись
            # "уезжает" внутрь неё и становится тёмной — иначе либо сливается
            # с дорожкой, либо (если красить всегда тёмным) теряется на
            # тёмном фоне, пока заливка до неё не дошла.
            # Показываем именно ИСПОЛЬЗОВАННЫЙ процент (win["used"]), а не
            # оставшийся (win["left"]) — иначе число визуально не совпадает
            # с заливкой: например, при 2% использования заливка почти
            # пустая, а подпись показывала бы "98%" (сколько осталось), что
            # выглядит как ошибка. win["left"] по-прежнему используется в
            # tooltip_text(), где явно написано слово "осталось".
            pct_text = f'{round(win["used"])}%'
            probe = c.create_text(0, 0, text=pct_text, font=FONT_PCT)
            bbox = c.bbox(probe)
            label_px_w = (bbox[2] - bbox[0]) if bbox else 18
            c.delete(probe)
            label_right, dark = model.label_position(BAR_W, fill_w, label_px_w)
            c.create_text(
                BAR_X + label_right, y + BAR_H / 2, anchor="e", text=pct_text,
                fill=(TEXT_DARK if dark else TEXT), font=FONT_PCT,
            )

            y += BAR_H

            # Время до сброса — под КАЖДОЙ шкалой у которой оно известно.
            if win["reset"]:
                c.create_text(BAR_X, y + RESET_H / 2 + 1, anchor="w", text=win["reset"], fill=MUTED, font=FONT_RESET)
                y += RESET_H

            y += ROW_GAP
