"""Громкость и выбор устройств на главной: все обращения к Windows идут через SystemHub (отдельный поток)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor


class AudioMixin:
    """Часть класса Island: AudioMixin."""

    def audio_state(s) -> dict:
        return s.hub.state.get('audio', {})

    def volume(s):
        v = s.audio_state().get('out', {}).get('volume')
        return 50 if v is None else v

    def set_volume(s, v):
        """Пользователь двигает ползунок: показываем значение сразу, в Windows оно уходит в фоне."""
        s.vn.setText(str(v))
        s.hub.set_volume(v)

    def apply_audio_snapshot(s, a):
        """Приходит из SystemHub: на главной показывается РЕАЛЬНОЕ состояние устройства по умолчанию."""
        out = a.get('out', {})
        v = out.get('volume')
        if v is not None and not s.vol.drag:
            s.vol.setValue(v)
            s.vn.setText('🔇' if out.get('muted') else str(v))
        cur = next((d for d in out.get('devices', []) if d['default']), None)
        fm = s.dev_btn.fontMetrics()
        s.dev_btn.setText((fm.elidedText(cur['name'], Qt.ElideRight, 120) if cur else 'Нет устройства') + ' ▾')
        s.dev_btn.setToolTip(cur['name'] if cur else '')

    def pick_audio_device(s):
        """Меню реальных устройств: выбор меняет устройство по умолчанию в Windows, а не подпись кнопки."""
        a = s.audio_state()
        m = s.mk_menu()
        any_dev = False
        for key, title in (('out', 'Вывод звука'), ('in', 'Ввод звука (микрофон)')):
            devs = a.get(key, {}).get('devices', [])
            if not devs:
                continue
            any_dev = True
            h = m.addAction(title)
            h.setEnabled(False)
            for d in devs:
                act = m.addAction(d['name'][:46])
                act.setCheckable(True)
                act.setChecked(d['default'])
                act.triggered.connect(lambda _=False, dev=d: s.hub.set_default_device(dev['id'], dev['name']))
            m.addSeparator()
        if not any_dev:
            m.addAction('Аудиоустройства не найдены').setEnabled(False)
        m.exec(QCursor.pos())
