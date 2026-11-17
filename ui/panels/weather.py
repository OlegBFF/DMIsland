"""Панель «weather»."""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from ui.themes import FD


class WeatherPanel:
    """Часть класса Island: WeatherPanel."""

    def pg_weather(s):
        w, h = QWidget(), QHBoxLayout()
        w.setLayout(h)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        sky = QFrame()
        sky.setObjectName('skycard')
        sv = QVBoxLayout(sky)
        sv.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        s.w_city = QLabel(s.cfg['city'])
        s.w_city.setStyleSheet('font-weight:600;font-size:13px')
        b_ref = s.btn('↻', s.fetch_weather)
        b_ref.setFixedSize(28, 28)
        top.addWidget(s.w_city)
        top.addStretch()
        top.addWidget(b_ref)
        sv.addLayout(top)

        s.w_big = QLabel('--°')
        s.w_big.setStyleSheet(f'font-family:{FD};font-size:44px;font-weight:700')
        s.w_desc = QLabel('Загрузка прогноза…')
        s.w_desc.setStyleSheet('font-size:12.5px;font-weight:600')
        sv.addWidget(s.w_big)
        sv.addWidget(s.w_desc)
        sv.addStretch()

        pills = QHBoxLayout()
        s.w_wind = QLabel('0 м/с')
        s.w_hum = QLabel('0%')
        s.w_prcp = QLabel('0 мм')
        for p_lb in (s.w_wind, s.w_hum, s.w_prcp):
            p_lb.setStyleSheet('background:rgba(0,0,0,45);padding:6px 8px;border-radius:10px;font-size:11px')
            pills.addWidget(p_lb)
        sv.addLayout(pills)
        h.addWidget(sky, 2)

        right = QVBoxLayout()
        right.setSpacing(8)
        hcard = QFrame()
        hcard.setObjectName('bento')
        s.w_hourly_layout = QHBoxLayout(hcard)
        s.w_hourly_layout.setContentsMargins(10, 8, 10, 8)
        right.addWidget(hcard)

        dcard = QFrame()
        dcard.setObjectName('bento')
        s.w_daily_layout = QVBoxLayout(dcard)
        s.w_daily_layout.setContentsMargins(12, 8, 12, 8)
        s.w_daily_layout.setSpacing(4)
        right.addWidget(dcard, 1)

        h.addLayout(right, 3)
        return w
