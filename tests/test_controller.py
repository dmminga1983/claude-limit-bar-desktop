from app.controller import Controller


class FakeCfg:
    def __init__(self, **kw):
        self.d = {"tray_enabled": True, "overlay_enabled": True}
        self.d.update(kw)

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v


class FakeTray:
    def __init__(self):
        self.running = False
        self.updates = []

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def update(self, data):
        self.updates.append(data)


class FakeOverlay:
    def __init__(self):
        self.visible = None
        self.updates = []
        self.mode = None

    def set_visible(self, v):
        self.visible = v

    def update(self, data):
        self.updates.append(data)

    def set_mode(self, mode):
        self.mode = mode


def make(**cfg):
    c, t, o = FakeCfg(**cfg), FakeTray(), FakeOverlay()
    quits = []
    ctl = Controller(c, t, o, on_quit=lambda: quits.append(1))
    return ctl, c, t, o, quits


def test_initial_both_on():
    ctl, c, t, o, _ = make()
    ctl.apply_initial()
    assert t.running and o.visible is True


def test_initial_overlay_off_tray_on():
    ctl, c, t, o, _ = make(overlay_enabled=False)
    ctl.apply_initial()
    assert t.running and o.visible is False


def test_initial_tray_off_overlay_on():
    ctl, c, t, o, _ = make(tray_enabled=False)
    ctl.apply_initial()
    assert not t.running and o.visible is True


def test_initial_both_off_forces_tray_on():
    ctl, c, t, o, _ = make(tray_enabled=False, overlay_enabled=False)
    ctl.apply_initial()
    assert t.running and c.get("tray_enabled") is True and o.visible is False


def test_overlay_can_be_turned_off_when_tray_on():
    ctl, c, t, o, _ = make()
    ctl.apply_initial()
    ctl.set_overlay(False)
    assert o.visible is False and c.get("overlay_enabled") is False and t.running


def test_tray_can_be_turned_off_when_overlay_on():
    ctl, c, t, o, _ = make()
    ctl.apply_initial()
    ctl.set_tray(False)
    assert not t.running and c.get("tray_enabled") is False and o.visible is True


def test_turning_off_last_visible_one_enables_the_other_overlay_case():
    ctl, c, t, o, _ = make(tray_enabled=False)
    ctl.apply_initial()
    ctl.set_overlay(False)  # tray был выключен -> включится сам
    assert t.running and c.get("tray_enabled") is True
    assert o.visible is False


def test_turning_off_last_visible_one_enables_the_other_tray_case():
    ctl, c, t, o, _ = make(overlay_enabled=False)
    ctl.apply_initial()
    ctl.set_tray(False)  # overlay был выключен -> включится сам
    assert o.visible is True and c.get("overlay_enabled") is True
    assert not t.running


def test_toggles():
    ctl, c, t, o, _ = make()
    ctl.apply_initial()
    ctl.toggle_overlay()
    assert c.get("overlay_enabled") is False
    ctl.toggle_overlay()
    assert c.get("overlay_enabled") is True and o.visible is True
    ctl.toggle_tray()
    assert c.get("tray_enabled") is False and not t.running
    ctl.toggle_tray()
    assert c.get("tray_enabled") is True and t.running


def test_push_updates_both_and_tray_gets_last_data_when_reenabled():
    ctl, c, t, o, _ = make()
    ctl.apply_initial()
    ctl.push({"x": 1})
    assert t.updates == [{"x": 1}] and o.updates == [{"x": 1}]
    ctl.set_tray(False)
    ctl.push({"x": 2})
    assert t.updates == [{"x": 1}]  # выключенный трей не обновляется
    assert o.updates[-1] == {"x": 2}
    ctl.set_tray(True)
    assert t.updates[-1] == {"x": 2}  # включили — сразу получил свежие данные


def test_quit_calls_callback():
    ctl, *_, quits = make()
    ctl.quit()
    assert quits == [1]


def test_get_overlay_mode_defaults_to_always():
    ctl, c, t, o, _ = make()
    assert ctl.get_overlay_mode() == "always"


def test_set_overlay_mode_updates_config_and_overlay():
    ctl, c, t, o, _ = make()
    ctl.set_overlay_mode("claude_only")
    assert c.get("overlay_mode") == "claude_only"
    assert o.mode == "claude_only"
    assert ctl.get_overlay_mode() == "claude_only"
