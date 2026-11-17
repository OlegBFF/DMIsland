"""Погода."""
import json
import threading
import urllib.parse
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from core.security import safe_urlopen


class WeatherMixin:
    """Часть класса Island: WeatherMixin."""

    def fetch_weather(s):
        def run():
            try:
                city = urllib.parse.quote(s.cfg.get('city', 'Москва'))
                g = json.loads(safe_urlopen(
                    f"https://geocoding-api.open-meteo.com/v1/search?count=1&language=ru&name={city}", timeout=8
                ).decode('utf-8'))['results'][0]
                lat, lon = g['latitude'], g['longitude']
                url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                       "&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code"
                       "&hourly=temperature_2m,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
                       "&timezone=auto")
                w = json.loads(safe_urlopen(url, timeout=8).decode('utf-8'))
                cur = w['current']
                s.weatherReady.emit({
                    'temp': round(cur['temperature_2m']),
                    'hum': round(cur['relative_humidity_2m']),
                    'wind': round(cur['wind_speed_10m'], 1),
                    'prcp': round(cur['precipitation'], 1),
                    'hourly': list(zip(w['hourly']['time'][:8], w['hourly']['temperature_2m'][:8])),
                    'daily': list(zip(w['daily']['time'][:7], w['daily']['temperature_2m_min'][:7],
                                      w['daily']['temperature_2m_max'][:7], w['daily']['precipitation_sum'][:7]))
                })
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def on_weather_data(s, d):
        s.weather_data = d
        s.w_city.setText(s.cfg['city'])
        s.w_big.setText(f"{d['temp']}°")
        s.w_desc.setText('Погода в реальном времени')
        s.w_wind.setText(f"{d['wind']} м/с")
        s.w_hum.setText(f"{d['hum']}%")
        s.w_prcp.setText(f"{d['prcp']} мм")

        while s.w_hourly_layout.count():
            w = s.w_hourly_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        for tm, tp in d.get('hourly', []):
            col = QWidget()
            cv = QVBoxLayout(col)
            cv.setContentsMargins(2, 2, 2, 2)
            l1 = QLabel(tm[-5:])
            l1.setStyleSheet('color:rgba(255,255,255,140);font-size:10px')
            l3 = QLabel(f"{round(tp)}°")
            l3.setStyleSheet('font-weight:600;font-size:11.5px')
            for lb in (l1, l3):
                lb.setAlignment(Qt.AlignCenter)
                cv.addWidget(lb)
            s.w_hourly_layout.addWidget(col)

        while s.w_daily_layout.count():
            w = s.w_daily_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        days_ru = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        for idx, (dt, tmin, tmax, pr) in enumerate(d.get('daily', [])):
            row = QWidget()
            rh = QHBoxLayout(row)
            rh.setContentsMargins(0, 0, 0, 0)
            dn = 'Сегодня' if idx == 0 else days_ru[datetime.strptime(dt, '%Y-%m-%d').weekday()]
            l_d = QLabel(dn)
            l_d.setFixedWidth(56)
            l_min = QLabel(f"{round(tmin)}°")
            l_min.setStyleSheet('color:rgba(255,255,255,140)')
            bar = QFrame()
            bar.setFixedHeight(4)
            bar.setStyleSheet('background:#ff9f0a;border-radius:2px')
            l_max = QLabel(f"{round(tmax)}°")
            l_max.setStyleSheet('font-weight:600')
            l_pr = QLabel(f"{round(pr, 1)} мм")
            l_pr.setFixedWidth(48)
            l_pr.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            l_pr.setStyleSheet('color:#5ac8fa;font-size:10.5px')
            for w_el in (l_d, l_min, bar, l_max, l_pr):
                rh.addWidget(w_el)
            s.w_daily_layout.addWidget(row)
