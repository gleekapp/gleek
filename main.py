import sys, os, math, random, time, weakref, re, urllib.request, json, shutil, subprocess
from PyQt6.QtCore import (Qt, QPointF, QRectF, QTimer, QEasingCurve,
                          QPropertyAnimation, QVariantAnimation, pyqtProperty, QUrl,
                          QSettings, QEvent, QObject, QRunnable, QThreadPool,
                          pyqtSignal, pyqtSlot)
from PyQt6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen, QBrush,
                         QLinearGradient, QRadialGradient, QCursor, QDesktopServices,
                         QPixmap, QIcon, QShortcut, QKeySequence)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QStackedWidget, QLineEdit, QFrame,
                             QGraphicsOpacityEffect, QScrollArea, QDialog,
                             QSystemTrayIcon, QMenu, QListWidget)
from supabase_auth import (
    SupabaseAuthClient, SupabaseAuthError, SupabaseConfigurationError,
    WindowsSessionStore,
)
from chat_crypto import (
    ChatCryptoError,
    decrypt_message,
    encrypt_message,
    generate_identity,
    public_key_for_private,
)


class _ChatTaskSignals(QObject):
    finished = pyqtSignal(object, object)


class _ChatTask(QRunnable):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.signals = _ChatTaskSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self.callback()
        except (SupabaseAuthError, ChatCryptoError) as exc:
            self.signals.finished.emit(None, str(exc))
        else:
            self.signals.finished.emit(result, None)


# ---------- palette: cool graphite, one seafoam accent, one blue for depth ----------
CURRENT_VERSION = "1.0.3"
# Use the RAW link to the version.json on GitHub
UPDATE_URL = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/version.json"
# The link to the ZIP of your main branch
REPO_ZIP_URL = "https://github.com/YOUR_USERNAME/YOUR_REPO/archive/refs/heads/main.zip"

BG_TOP, BG_BOT = "#0B0F14", "#0E151D"
SURFACE, SURF_HI = "#121A23", "#18222D"
INPUT_BG, BORDER = "#0E141B", "#223040"
TEXT, MUTED, INK = "#E8EDF2", "#8595A8", "#06201B"
ACCENT, BLUE, AMBER, ERR = "#7DD3C0", "#4F7CFF", "#F2B872", "#F0707A"
# Demo inventory; replace this with a real device source when device management is added.
DEVICES = {
    "Dev-1": ("192.168.1.21", "online"),
    "Dev-2": ("192.168.1.22", "online"),
    "Dev-3": ("192.168.1.23", "idle"),
    "Dev-4": ("192.168.1.24", "online"),
    "Dev-5": ("192.168.1.25", "offline"),
}

def mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(*(int(x + (y - x) * t) for x, y in
                    ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))))

def alpha(c, a):
    c = QColor(c); c.setAlphaF(max(0.0, min(1.0, a))); return c

def smooth(cur, target, dt, rate):          # frame-rate independent easing
    return cur + (target - cur) * (1 - math.exp(-dt * rate))

def text(s, size, weight=QFont.Weight.Normal, color=TEXT):
    l = QLabel(s)
    f = QFont(); f.setPixelSize(size); f.setWeight(weight); l.setFont(f)
    l.setStyleSheet(f"color:{color};")
    return l


# ---------- shared light-follows-cursor behaviour ----------
LIVE = weakref.WeakSet()

class Glow:
    glow_radius, glow_strength, glow_color = 130, 1.0, ACCENT

    def _glow_init(self):
        self._lvl = self._hov = self._prs = 0.0
        self._gx = self._gy = 0.0
        self._ripples = []
        LIVE.add(self)

    def extra_tick(self, dt):
        return False

    def glow_tick(self, dt, cur):
        p, r = self.mapFromGlobal(cur), self.rect()
        dx = max(r.left() - p.x(), 0, p.x() - r.right())
        dy = max(r.top() - p.y(), 0, p.y() - r.bottom())
        near = max(0.0, 1 - math.hypot(dx, dy) / self.glow_radius) ** 1.6
        if self._lvl < 0.01:
            self._gx, self._gy = p.x(), p.y()
        else:
            self._gx, self._gy = smooth(self._gx, p.x(), dt, 12), smooth(self._gy, p.y(), dt, 12)
        self._lvl = smooth(self._lvl, near, dt, 6)
        self._hov = smooth(self._hov, 1.0 if r.contains(p) else 0.0, dt, 9)
        down = self.isDown() if hasattr(self, "isDown") else False
        self._prs = smooth(self._prs, 1.0 if down else 0.0, dt, 16)
        self._ripples = [(x, y, a + dt) for x, y, a in self._ripples if a < 0.8]
        busy = self.extra_tick(dt)
        if busy or self._ripples or max(self._lvl, self._hov, self._prs) > 0.003:
            self.update()

    def paint_glow(self, p, path, fill=0.12, border=0.7):
        if self._lvl < 0.004:
            return
        k, R, pos = self._lvl * self.glow_strength, self.glow_radius * 1.1, QPointF(self._gx, self._gy)
        g = QRadialGradient(pos, R)
        g.setColorAt(0, alpha(self.glow_color, fill * k)); g.setColorAt(1, alpha(self.glow_color, 0))
        p.fillPath(path, QBrush(g))
        g = QRadialGradient(pos, R * 0.9)
        g.setColorAt(0, alpha(self.glow_color, border * k)); g.setColorAt(1, alpha(self.glow_color, 0))
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QBrush(g), 1.4)); p.drawPath(path)


def rounded(r, rad):
    path = QPainterPath(); path.addRoundedRect(r, rad, rad); return path


PREFS = (
    ("low_power", "Low power mode", "Use a slower, simpler animated background.", False),
    ("tray", "Keep running in tray", "Closing the window keeps Gleek running.", True),
    ("notify", "Desktop notifications", "Notify me about pairing requests.", True),
    ("autostart", "Start with Windows", "Launch Gleek when you sign in.", False),
)


def make_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 64, 64)
    gradient.setColorAt(0, QColor(ACCENT))
    gradient.setColorAt(1, QColor(BLUE))
    painter.fillPath(rounded(QRectF(0, 0, 64, 64), 18), QBrush(gradient))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(INK), 3.4))
    painter.drawEllipse(QPointF(32, 32), 14, 14)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(INK))
    painter.drawEllipse(QPointF(32, 32), 4.5, 4.5)
    painter.end()
    return QIcon(pixmap)


def set_autostart(enabled):
    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}"'
            else:
                command = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            winreg.SetValueEx(key, "Gleek", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "Gleek")
            except FileNotFoundError:
                pass


class Palette(QDialog):
    def __init__(self, parent, items):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.items = items
        self.setFixedWidth(460)
        self.setStyleSheet(
            f"QDialog{{background:{SURFACE};border:1px solid {BORDER};}}"
            f"QLineEdit{{background:{INPUT_BG};border:1px solid {BORDER};border-radius:10px;"
            f"padding:10px 12px;color:{TEXT};font-size:14px;}}"
            f"QListWidget{{background:transparent;border:none;color:{TEXT};font-size:14px;outline:none;}}"
            f"QListWidget::item{{padding:9px 12px;border-radius:8px;}}"
            f"QListWidget::item:selected{{background:{SURF_HI};color:{ACCENT};}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.box = QLineEdit()
        self.box.setPlaceholderText("Type a command...")
        self.list = QListWidget()
        self.list.setFixedHeight(230)
        layout.addWidget(self.box)
        layout.addWidget(self.list)
        self.box.textChanged.connect(self.refilter)
        self.box.returnPressed.connect(self.run)
        self.list.itemActivated.connect(lambda _item: self.run())
        self.box.installEventFilter(self)
        self.refilter("")

    def refilter(self, query):
        self.list.clear()
        for label, _action in self.items:
            if query.casefold() in label.casefold():
                self.list.addItem(label)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, watched, event):
        if watched is self.box and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.list.count():
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                row = self.list.currentRow() + step
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
        return super().eventFilter(watched, event)

    def run(self):
        item = self.list.currentItem()
        if item is not None:
            action = dict(self.items)[item.text()]
            self.accept()
            QTimer.singleShot(0, action)


class ChatDialog(QDialog):
    def __init__(self, portal, peer_id, account, peer_public_key):
        super().__init__(portal)
        self.portal = portal
        self.peer_id = peer_id
        self.peer_public_key = peer_public_key
        self.setWindowTitle(f"Chat with {account}")
        self.resize(620, 520)
        self.setStyleSheet(
            f"QDialog{{background:{BG_BOT};}}"
            f"QListWidget{{background:{SURFACE};border:1px solid {BORDER};"
            f"border-radius:12px;color:{TEXT};padding:8px;}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(text(f"Chat with {account}", 22, QFont.Weight.DemiBold))
        notice = text(
            "Messages are encrypted on this device. The service sees account IDs and timing; "
            "public keys are delivered by the service.",
            12,
            color=MUTED,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.messages = QListWidget()
        layout.addWidget(self.messages, 1)
        self.status = text("", 12, color=MUTED)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Write a message...")
        self.input.setMaxLength(500)
        self.input.setFixedHeight(44)
        self.input.setStyleSheet(
            f"QLineEdit{{background:{INPUT_BG};border:1px solid {BORDER};"
            f"border-radius:10px;padding:0 12px;color:{TEXT};font-size:14px;}}"
        )
        self.send_button = GlowButton("Send", "primary")
        self.send_button.setFixedWidth(100)
        self.send_button.clicked.connect(self.send_message)
        self.input.returnPressed.connect(self.send_message)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setInterval(6000)
        self.timer.timeout.connect(self.refresh_messages)
        self.timer.start()
        self._refresh_task = None
        self._send_task = None
        QTimer.singleShot(0, self.refresh_messages)

    def refresh_messages(self):
        if self._refresh_task is not None:
            return

        def load_messages():
            entries = self.portal.auth_client.get_encrypted_pairing_messages(
                self.peer_id, self.portal.access_token
            )
            rendered = []
            for entry in entries:
                sender_id = entry["sender_id"]
                recipient_id = (
                    self.peer_id if sender_id == self.portal.user_id
                    else self.portal.user_id
                )
                body = decrypt_message(
                    entry["envelope"],
                    self.portal.chat_private_key,
                    sender_id,
                    recipient_id,
                )
                author = "You" if sender_id == self.portal.user_id else "Paired account"
                rendered.append((entry.get("id"), f"{author}: {body}"))
            return rendered

        task = _ChatTask(load_messages)
        task.signals.finished.connect(self._on_messages_loaded)
        self._refresh_task = task
        QThreadPool.globalInstance().start(task)

    @pyqtSlot(object, object)
    def _on_messages_loaded(self, rendered, error):
        self._refresh_task = None
        if error is not None:
            self.status.setText(error)
            self.status.setStyleSheet(f"color:{ERR};")
            return
        message_ids = [message_id for message_id, _ in rendered]
        if message_ids != getattr(self, "_message_ids", None):
            self.messages.clear()
            self.messages.addItems([body for _, body in rendered])
            if self.messages.count():
                self.messages.scrollToBottom()
            self._message_ids = message_ids
        self.status.setText(
            "Encrypted on this device. Public keys are supplied by the service."
        )
        self.status.setStyleSheet(f"color:{MUTED};")

    def send_message(self):
        if self._send_task is not None:
            return
        message = self.input.text().strip()
        if not message:
            return

        def send():
            sender_envelope = encrypt_message(
                message,
                public_key_for_private(self.portal.chat_private_key),
                self.portal.user_id,
                self.peer_id,
            )
            recipient_envelope = encrypt_message(
                message,
                self.peer_public_key,
                self.portal.user_id,
                self.peer_id,
            )
            self.portal.auth_client.send_encrypted_pairing_message(
                self.peer_id,
                sender_envelope,
                recipient_envelope,
                self.portal.access_token,
            )
            return message

        task = _ChatTask(send)
        task.signals.finished.connect(self._on_message_sent)
        self._send_task = task
        self.send_button.setEnabled(False)
        self.input.setEnabled(False)
        QThreadPool.globalInstance().start(task)

    @pyqtSlot(object, object)
    def _on_message_sent(self, sent_message, error):
        self._send_task = None
        self.send_button.setEnabled(True)
        self.input.setEnabled(True)
        if error is not None:
            self.status.setText(error)
            self.status.setStyleSheet(f"color:{ERR};")
            return
        if self.input.text().strip() == sent_message:
            self.input.clear()
        self.refresh_messages()

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


class GlowButton(QPushButton, Glow):
    def __init__(self, label, kind="secondary", parent=None):
        super().__init__(label, parent)
        self.kind, self.active, self._act = kind, False, 0.0
        self._glow_init()
        self.glow_color = "#FFFFFF" if kind == "primary" else ACCENT
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(46 if kind == "nav" else 44)
        f = self.font(); f.setPixelSize(14); f.setWeight(QFont.Weight.DemiBold); self.setFont(f)

    def set_active(self, v):
        self.active = v

    def extra_tick(self, dt):
        t = 1.0 if self.active else 0.0
        self._act = smooth(self._act, t, dt, 8)
        return abs(self._act - t) > 0.003

    def mousePressEvent(self, e):
        self._ripples.append((e.position().x(), e.position().y(), 0.0))
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(1.0 if self.isEnabled() else 0.4)
        s = self._prs * 1.5
        r = QRectF(self.rect()).adjusted(1 + s, 1 + s, -1 - s, -1 - s).translated(0, -1.2 * self._hov + 0.6 * self._prs)
        path = rounded(r, 12)
        if self.kind == "primary":
            fill = mix(ACCENT, "#FFFFFF", 0.16 * self._hov); border, ink = fill, QColor(INK)
        elif self.kind == "nav":
            fill, border = QColor(0, 0, 0, 0), QColor(0, 0, 0, 0)
            ink = mix(MUTED, TEXT, max(self._hov, self._act))
        else:
            fill, border, ink = mix(SURF_HI, "#243242", self._hov), mix(BORDER, "#35485C", self._hov), QColor(TEXT)
        p.fillPath(path, fill); p.setPen(QPen(border, 1)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
        self.paint_glow(p, path, 0.30 if self.kind == "primary" else 0.12, 0.8)
        p.save(); p.setClipPath(path); p.setPen(Qt.PenStyle.NoPen)
        for x, y, a in self._ripples:
            k = 1 - (1 - a / 0.8) ** 3
            p.setBrush(alpha(self.glow_color, 0.22 * (1 - k)))
            rad = k * max(r.width(), r.height()) * 1.2
            p.drawEllipse(QPointF(x, y), rad, rad)
        p.restore()
        p.setPen(ink); p.setFont(self.font())
        if self.kind == "nav":
            p.drawText(r.adjusted(18, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        else:
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text())


class AnimatedInput(QLineEdit, Glow):
    glow_radius = 110

    def __init__(self, placeholder, password=False):
        super().__init__()
        self.setPlaceholderText(placeholder)
        if password: self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setFixedHeight(48)
        self._glow_init(); self._foc = self._err = 0.0; self.error = False
        self.setStyleSheet(f"QLineEdit{{background:transparent;border:none;padding:0 16px;color:{TEXT};"
                           f"font-size:14px;selection-background-color:{ACCENT};selection-color:{INK};}}")
        self.textChanged.connect(lambda: setattr(self, "error", False))

    def extra_tick(self, dt):
        tf, te = (1.0 if self.hasFocus() else 0.0), (1.0 if self.error else 0.0)
        self._foc, self._err = smooth(self._foc, tf, dt, 9), smooth(self._err, te, dt, 8)
        return abs(self._foc - tf) > 0.003 or abs(self._err - te) > 0.003

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = rounded(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12)
        p.fillPath(path, QColor(INPUT_BG))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(ACCENT, 0.16 * self._foc), 3)); p.drawPath(path)
        p.setPen(QPen(mix(mix(BORDER, ACCENT, self._foc), ERR, self._err), 1)); p.drawPath(path)
        self.paint_glow(p, path, 0.07, 0.6)
        p.end()
        super().paintEvent(e)


class Card(QFrame, Glow):
    def __init__(self, radius=18, strength=0.7):
        super().__init__()
        self.radius, self.glow_strength, self.glow_radius = radius, strength, 200
        self._glow_init()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = rounded(QRectF(self.rect()).adjusted(1, 1, -1, -1), self.radius)
        p.fillPath(path, alpha(SURFACE, 0.84))
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(BORDER), 1)); p.drawPath(path)
        self.paint_glow(p, path, 0.08, 0.65)


class StatCard(Card):
    def __init__(self, label, value=""):
        super().__init__(16, 0.8)
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 22); lay.setSpacing(6)
        self.value = text(str(value), 34, QFont.Weight.DemiBold)
        lay.addWidget(text(label, 13, color=MUTED)); lay.addWidget(self.value)
        self.anim = QVariantAnimation(self); self.anim.setDuration(1100)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(lambda v: self.value.setText(str(int(round(v)))))

    def count_to(self, n):
        self.anim.stop(); self.anim.setStartValue(0.0); self.anim.setEndValue(float(n)); self.anim.start()


class StatusDot(QWidget):
    COL = {"online": ACCENT, "idle": AMBER, "offline": "#4A5868"}

    def __init__(self, state):
        super().__init__(); self.state = state; self.setFixedSize(16, 16); LIVE.add(self)

    def glow_tick(self, dt, cur):
        if self.state == "online": self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, ctr = QColor(self.COL[self.state]), QPointF(8, 8)
        if self.state == "online":
            ph = (time.perf_counter() % 2.6) / 2.6
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(alpha(c, 0.55 * (1 - ph)), 1.5))
            p.drawEllipse(ctr, 3.5 + 4 * ph, 3.5 + 4 * ph)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(c); p.drawEllipse(ctr, 3.5, 3.5)


class LogoMark(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(42, 42)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 42, 42); g.setColorAt(0, QColor(ACCENT)); g.setColorAt(1, QColor(BLUE))
        p.fillPath(rounded(QRectF(0, 0, 42, 42), 12), QBrush(g))
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(INK), 2.2)); p.drawEllipse(QPointF(21, 21), 9, 9)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(INK)); p.drawEllipse(QPointF(21, 21), 3, 3)


class Avatar(QWidget):
    def __init__(self, name):
        super().__init__(); self.name = name[:1].upper(); self.setFixedSize(36, 36)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 36, 36); g.setColorAt(0, QColor(ACCENT)); g.setColorAt(1, QColor(BLUE))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(QRectF(0, 0, 36, 36))
        p.setPen(QColor(INK)); f = self.font(); f.setPixelSize(15); f.setWeight(QFont.Weight.Bold); p.setFont(f)
        p.drawText(QRectF(0, 0, 36, 36), Qt.AlignmentFlag.AlignCenter, self.name)


# ---------- smooth page transitions ----------
class FadeStack(QStackedWidget):
    def __init__(self):
        super().__init__(); self._anim = None; self._target = None

    def _run(self, a, b, ms, curve, done=None):
        eff = QGraphicsOpacityEffect(self); eff.setOpacity(a); self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setStartValue(a); anim.setEndValue(b); anim.setDuration(ms); anim.setEasingCurve(curve)
        def fin():
            if b >= 1: self.setGraphicsEffect(None)   # no offscreen rendering when idle
            if done: done()
        anim.finished.connect(fin); self._anim = anim; anim.start()

    def fade_in(self):
        self._run(0.0, 1.0, 700, QEasingCurve.Type.OutCubic)

    def fade_to(self, w):
        if self._anim: self._anim.stop()
        if w is self.currentWidget() and self._target is None: return
        self._target = w
        def swap():
            self.setCurrentWidget(w); self._target = None
            self._run(0.0, 1.0, 420, QEasingCurve.Type.OutCubic)
        self._run(1.0 if self.graphicsEffect() is None else self.graphicsEffect().opacity(),
                  0.0, 220, QEasingCurve.Type.InCubic, swap)


class Sidebar(QFrame):
    def __init__(self):
        super().__init__(); self._y = 0.0; self._btn = None
        self._anim = QPropertyAnimation(self, b"indY", self)
        self._anim.setDuration(520); self._anim.setEasingCurve(QEasingCurve.Type.OutQuint)

    def get_y(self): return self._y
    def set_y(self, v): self._y = v; self.update()
    indY = pyqtProperty(float, get_y, set_y)

    def goto(self, btn, animate=True):
        self._btn = btn; self._anim.stop()
        if animate and self.isVisible():
            self._anim.setStartValue(self._y); self._anim.setEndValue(float(btn.y())); self._anim.start()
        else:
            self._y = float(btn.y()); self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._btn and self._anim.state() != QPropertyAnimation.State.Running:
            self._y = float(self._btn.y())

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), alpha("#0A0E13", 0.78))
        p.setPen(QColor(BORDER)); p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        if self._btn:
            b = self._btn
            r = QRectF(b.x(), self._y, b.width(), b.height())
            p.fillPath(rounded(r, 12), alpha(ACCENT, 0.09))
            p.fillPath(rounded(QRectF(r.x(), r.y() + 12, 3, r.height() - 24), 1.5), QColor(ACCENT))


# ---------- animated backdrop ----------
class Stage(QWidget):
    def __init__(self):
        super().__init__()
        self.t0 = self.last = time.perf_counter(); self.t = 0.0; self.mx = self.my = None
        self.low_power = False
        self._background = QPixmap()
        self.parts = [[random.uniform(0, 1180), random.uniform(0, 740), random.uniform(-9, 9),
                       random.uniform(-9, 9), random.uniform(1.0, 2.4), random.uniform(0, 6.28)] for _ in range(38)]
        self.timer = QTimer(self); self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick); self.timer.start(16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cache_background()

    def _cache_background(self):
        size = self.size()
        if size.isEmpty():
            self._background = QPixmap()
            return
        self._background = QPixmap(size)
        painter = QPainter(self._background)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 0, size.height())
        gradient.setColorAt(0, QColor(BG_TOP))
        gradient.setColorAt(1, QColor(BG_BOT))
        painter.fillRect(QRectF(0, 0, size.width(), size.height()), gradient)
        radius = max(size.width(), size.height()) * 0.55
        for color, x, y, opacity in (
            (BLUE, 0.18, 0.25, 0.15),
            (ACCENT, 0.85, 0.80, 0.11),
            (BLUE, 0.70, 0.10, 0.07),
        ):
            center = QPointF(size.width() * x, size.height() * y)
            radial = QRadialGradient(center, radius)
            radial.setColorAt(0, alpha(color, opacity))
            radial.setColorAt(1, alpha(color, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(radial))
            painter.drawEllipse(center, radius, radius)
        painter.end()

    def set_low_power(self, enabled):
        self.low_power = enabled
        self.timer.setInterval(50 if enabled else 16)

    def tick(self):
        if not self.isVisible() or self.window().isMinimized():
            self.last = time.perf_counter()
            return
        now = time.perf_counter(); dt = min(now - self.last, 0.05); self.last = now; self.t = now - self.t0
        cur = QCursor.pos(); lp = self.mapFromGlobal(cur)
        if self.mx is None: self.mx, self.my = lp.x(), lp.y()
        self.mx, self.my = smooth(self.mx, lp.x(), dt, 2.6), smooth(self.my, lp.y(), dt, 2.6)
        w, h = self.width(), self.height()
        for q in self.parts:
            q[0] = (q[0] + q[2] * dt + 20) % (w + 40) - 20
            q[1] = (q[1] + q[3] * dt + 20) % (h + 40) - 20
        for wd in list(LIVE):
            try:
                if wd.isVisible(): wd.glow_tick(dt, cur)
            except RuntimeError:
                pass
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h, t = self.width(), self.height(), self.t
        if self._background.size() != self.size():
            self._cache_background()
        p.drawPixmap(0, 0, self._background)
        if self.mx is not None:
            rg = QRadialGradient(QPointF(self.mx, self.my), 300)
            rg.setColorAt(0, alpha(ACCENT, .07)); rg.setColorAt(1, alpha(ACCENT, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(self.mx, self.my), 300, 300)
        pts = self.parts
        for i, a in (enumerate(pts) if not self.low_power else ()):
            for b in pts[i + 1:]:
                d = math.hypot(a[0] - b[0], a[1] - b[1])
                if d < 140:
                    p.setPen(QPen(alpha(ACCENT, .10 * (1 - d / 140)), 1)); p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            if self.mx is not None:
                d = math.hypot(a[0] - self.mx, a[1] - self.my)
                if d < 170:
                    p.setPen(QPen(alpha(ACCENT, .22 * (1 - d / 170)), 1)); p.drawLine(QPointF(a[0], a[1]), QPointF(self.mx, self.my))
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, _, _, s, ph in pts:
            p.setBrush(alpha(ACCENT, .30 + .18 * math.sin(t * 1.1 + ph))); p.drawEllipse(QPointF(x, y), s, s)


# ---------- the app ----------
class Portal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.prefs = QSettings("Gleek", "Gleek")
        self._quitting = False
        self._tray_hint = False
        self.setWindowIcon(make_icon())
        self.setWindowTitle("Gleek"); self.resize(1180, 740); self.setMinimumSize(1000, 660)
        geometry = self.prefs.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.user, self.user_id, self.access_level, self._first = None, None, None, True
        self.access_token = self.refresh_token = None
        self.chat_private_key = None
        self.chat_available = False
        self.chat_setup_error = ""
        self.chat_dialogs = {}
        self._known_pairing_requests = set()
        self.is_signing_up = False
        try:
            self.auth_client = SupabaseAuthClient.from_environment()
            self.auth_setup_error = ""
        except SupabaseConfigurationError as exc:
            self.auth_client = None
            self.auth_setup_error = str(exc)
        try:
            self.session_store = WindowsSessionStore()
            self.session_store_error = ""
        except OSError as exc:
            self.session_store = None
            self.session_store_error = str(exc)
        self.stage = Stage(); self.setCentralWidget(self.stage)
        self.stage.set_low_power(self.pref("low_power", False))
        self.pairing_timer = QTimer(self); self.pairing_timer.setInterval(8000)
        self.pairing_timer.timeout.connect(self.refresh_pairing_state)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh_access_token)
        lay = QVBoxLayout(self.stage); lay.setContentsMargins(0, 0, 0, 0)
        self.root = FadeStack(); lay.addWidget(self.root)
        self.build_login(); self.build_main()
        self.root.setCurrentWidget(self.login_page)
        self._init_tray()
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.open_palette)
        for index in range(4):
            QShortcut(
                QKeySequence(f"Ctrl+{index + 1}"),
                self,
                activated=lambda index=index: self.go(index),
            )
        QTimer.singleShot(0, self.restore_saved_session)
        QTimer.singleShot(1000, self.check_for_updates)

    def _init_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip("Gleek")
        menu = QMenu(self)
        open_action = menu.addAction("Open Gleek")
        open_action.triggered.connect(self.show_from_tray)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_from_tray()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.messageClicked.connect(self.open_pairing)
        self.tray.show()

    def go(self, index):
        if self.user and 0 <= index < len(self.navs):
            self.nav(self.navs[index], self.tabs.widget(index))

    def open_palette(self):
        if not self.user:
            return
        commands = [
            (f"Go to {name}", lambda index=index: self.go(index))
            for index, name in enumerate(("Dashboard", "Devices", "Pairing", "Settings"))
        ]
        commands.extend((
            ("Copy pairing code", self.copy_pairing_code),
            (
                "Toggle low power mode",
                lambda: self.set_pref("low_power", not self.pref("low_power", False)),
            ),
            ("Sign out", self.logout),
        ))
        Palette(self, commands).exec()

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_pairing(self):
        self.show_from_tray()
        self.go(2)

    def check_for_updates(self):
        def task():
            try:
                with urllib.request.urlopen(UPDATE_URL, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    remote_version = data.get("version")
                    if remote_version and remote_version != CURRENT_VERSION:
                        print(f"Update found: {remote_version}. Starting silent update...")
                        QTimer.singleShot(0, lambda: self.start_silent_update())
            except Exception as exc:
                print(f"Update check failed: {exc}", file=sys.stderr)

        QThreadPool.globalInstance().start(_ChatTask(task))

    def start_silent_update(self):
        try:
            # 1. Download the new version ZIP
            print("Downloading update...")
            with urllib.request.urlopen(REPO_ZIP_URL, timeout=15) as response:
                with open("update_package.zip", "wb") as f:
                    f.write(response.read())

            # 2. Create the update batch file
            app_path = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
            folder_path = os.path.dirname(app_path)

            batch_content = f"""@echo off
echo Updating Gleek...
timeout /t 2 /nobreak > nul
powershell -Command "Expand-Archive -Path 'update_package.zip' -DestinationPath '.' -Force"
del update_package.zip
start "" "{app_path}"
del "%~f0"
"""
            with open("update_gleek.bat", "w") as f:
                f.write(batch_content)

            # 3. Launch the batch file and exit
            subprocess.Popen(["update_gleek.bat"], shell=True)
            self.quit_app()

        except Exception as exc:
            print(f"Silent update failed: {exc}", file=sys.stderr)

    def quit_app(self):
        if self._quitting:
            return
        self._quitting = True
        self.pairing_timer.stop()
        self.refresh_timer.stop()
        try:
            if self.access_token and self.auth_client is not None:
                self.auth_client.clear_presence(self.access_token)
        except SupabaseAuthError as exc:
            print(f"Could not clear Gleek presence before exit: {exc}", file=sys.stderr)
        finally:
            if self.tray is not None:
                self.tray.hide()
            QApplication.quit()

    def closeEvent(self, event):
        self.prefs.setValue("geometry", self.saveGeometry())
        if (
            self.user
            and self.pref("tray", True)
            and self.tray is not None
            and QSystemTrayIcon.isSystemTrayAvailable()
            and not self._quitting
        ):
            event.ignore()
            self.hide()
            if not self._tray_hint:
                self._tray_hint = True
                self.tray.showMessage(
                    "Gleek is still running",
                    "Use the tray icon to reopen or quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            return
        event.accept()
        self.quit_app()

    def showEvent(self, e):
        super().showEvent(e)
        if self._first:
            self._first = False; self.root.fade_in()
            try:  # dark title bar on Windows 10/11
                import ctypes
                ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(ctypes.c_int(1)), 4)
            except Exception:
                pass

    def build_login(self):
        self.login_page = QWidget(); row = QHBoxLayout(self.login_page)
        row.setContentsMargins(110, 40, 110, 40)
        brand = QVBoxLayout(); brand.setSpacing(14); brand.addStretch()
        brand.addWidget(LogoMark())
        brand.addWidget(text("Gleek", 44, QFont.Weight.DemiBold))
        sub = text("Every machine you look after, reachable from one window.", 17, color=MUTED)
        sub.setWordWrap(True); sub.setMaximumWidth(380); brand.addWidget(sub); brand.addStretch()
        row.addLayout(brand); row.addStretch()

        card = Card(24, 0.8); card.setFixedWidth(410); card.setMinimumHeight(540)
        c = QVBoxLayout(card); c.setContentsMargins(40, 34, 40, 30); c.setSpacing(11)
        self.auth_title = text("Sign in", 28, QFont.Weight.DemiBold)
        self.auth_subtitle = text(
            "Use your email to access your account. This device remembers your sign-in securely.",
            14, color=MUTED,
        )
        self.auth_subtitle.setWordWrap(True)
        c.addWidget(self.auth_title)
        c.addWidget(self.auth_subtitle); c.addSpacing(8)
        self.email_in = AnimatedInput("Email")
        self.pass_in = AnimatedInput("Password", True)
        self.confirm_in = AnimatedInput("Confirm password", True)
        self.confirm_in.hide()
        self.auth_message = text("", 12, color=ERR)
        self.auth_message.setWordWrap(True)
        self.auth_message.setMinimumHeight(34)
        self.auth_button = GlowButton("Sign in", "primary")
        self.auth_button.clicked.connect(self.submit_auth)
        self.mode_button = GlowButton("Create account")
        self.mode_button.clicked.connect(self.toggle_auth_mode)
        self.configure_button = GlowButton("Configure Supabase")
        self.configure_button.clicked.connect(self.configure_supabase)
        self.configure_button.setVisible(self.auth_client is None)
        for widget in (self.email_in, self.pass_in, self.confirm_in, self.auth_message):
            c.addWidget(widget)
        c.addSpacing(2); c.addWidget(self.auth_button); c.addWidget(self.mode_button)
        c.addWidget(self.configure_button); c.addStretch()
        for widget in (self.email_in, self.pass_in, self.confirm_in):
            widget.returnPressed.connect(self.submit_auth)
        row.addWidget(card, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.root.addWidget(self.login_page)

    def toggle_auth_mode(self):
        self.is_signing_up = not self.is_signing_up
        self.auth_title.setText("Create account" if self.is_signing_up else "Sign in")
        self.auth_subtitle.setText(
            "Create an account. This device will remember your sign-in securely."
            if self.is_signing_up
            else "Use your email to access your account. This device remembers your sign-in securely."
        )
        self.confirm_in.setVisible(self.is_signing_up)
        self.auth_button.setText("Create account" if self.is_signing_up else "Sign in")
        self.mode_button.setText(
            "Back to sign in" if self.is_signing_up else "Create account"
        )
        self.set_auth_message("")

    def set_auth_message(self, message, is_error=True):
        self.auth_message.setText(message)
        self.auth_message.setStyleSheet(f"color:{ERR if is_error else ACCENT};")

    def configure_supabase(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure Gleek")
        dialog.setFixedWidth(500)
        dialog.setStyleSheet(
            f"QDialog{{background:{BG_BOT};}}"
            f"QLabel{{color:{TEXT};}}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        heading = text("Connect Gleek to Supabase", 21, QFont.Weight.DemiBold)
        layout.addWidget(heading)
        instructions = text(
            "Enter your project's URL and publishable (or legacy anon) key from "
            "Supabase Project Settings > API. Never use a service_role or secret key.",
            13, color=MUTED,
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        layout.addWidget(text("Project URL", 13, QFont.Weight.DemiBold))
        url_input = AnimatedInput("https://your-project.supabase.co")
        layout.addWidget(url_input)
        layout.addWidget(text("Publishable / anon key", 13, QFont.Weight.DemiBold))
        key_input = AnimatedInput("Supabase publishable or anon key", True)
        layout.addWidget(key_input)
        error_label = text("", 12, color=ERR)
        error_label.setWordWrap(True)
        layout.addWidget(error_label)
        save_button = GlowButton("Save settings", "primary")
        cancel_button = GlowButton("Cancel")
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        def save_settings():
            try:
                self.auth_client = SupabaseAuthClient.save_configuration(
                    url_input.text(), key_input.text()
                )
            except SupabaseConfigurationError as exc:
                error_label.setText(str(exc))
                url_input.error = True
                key_input.error = True
                return
            dialog.accept()

        save_button.clicked.connect(save_settings)
        cancel_button.clicked.connect(dialog.reject)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.auth_setup_error = ""
            self.configure_button.hide()
            self.set_auth_message(
                "Supabase settings saved. You can now sign in or create an account.",
                is_error=False,
            )

    def submit_auth(self):
        email = self.email_in.text().strip()
        password = self.pass_in.text()
        if not email or not password:
            self.set_auth_message("Enter your email and password.")
            self.email_in.error = self.pass_in.error = True
            return
        if self.is_signing_up and password != self.confirm_in.text():
            self.set_auth_message("The passwords do not match.")
            self.pass_in.error = self.confirm_in.error = True
            return
        if self.auth_client is None:
            self.set_auth_message(self.auth_setup_error)
            return

        self.auth_button.setEnabled(False)
        self.auth_button.setText("Please wait...")
        try:
            if self.is_signing_up:
                result = self.auth_client.sign_up(email, password)
                user_data = result.get("user")
                if not isinstance(user_data, dict):
                    raise SupabaseAuthError("Supabase did not return the new account.")
                if result.get("access_token"):
                    self.open_account(
                        user_data,
                        result["access_token"],
                        result.get("refresh_token"),
                        result.get("expires_in"),
                    )
                else:
                    self.toggle_auth_mode()
                    self.set_auth_message(
                        "Account created. Check your email to confirm it, then sign in.",
                        is_error=False,
                    )
            else:
                result = self.auth_client.sign_in(email, password)
                if not result.get("access_token"):
                    raise SupabaseAuthError("Supabase did not return a sign-in session.")
                if not result.get("refresh_token"):
                    raise SupabaseAuthError(
                        "Supabase did not return a refresh token, so this sign-in "
                        "cannot be saved on this device."
                    )
                user_data = result.get("user")
                if not isinstance(user_data, dict):
                    raise SupabaseAuthError("Supabase did not return the signed-in account.")
                self.open_account(
                    user_data,
                    result["access_token"],
                    result["refresh_token"],
                    result.get("expires_in"),
                )
        except SupabaseAuthError as exc:
            self.set_auth_message(str(exc))
            self.email_in.error = self.pass_in.error = True
        finally:
            self.auth_button.setEnabled(True)
            self.auth_button.setText("Create account" if self.is_signing_up else "Sign in")

    def restore_saved_session(self):
        if self.auth_client is None or self.session_store is None:
            return
        try:
            refresh_token = self.session_store.load_refresh_token()
            if refresh_token is None:
                return
            result = self.auth_client.refresh_session(refresh_token)
            access_token = result.get("access_token")
            rotated_refresh_token = result.get("refresh_token")
            user_data = result.get("user")
            if not isinstance(access_token, str) or not access_token:
                raise SupabaseAuthError("Supabase did not return a renewed access token.")
            if not isinstance(rotated_refresh_token, str) or not rotated_refresh_token:
                raise SupabaseAuthError("Supabase did not return a renewed refresh token.")
            if not isinstance(user_data, dict):
                raise SupabaseAuthError("Supabase did not return the saved account.")
            self.open_account(
                user_data,
                access_token,
                rotated_refresh_token,
                result.get("expires_in"),
            )
        except SupabaseAuthError as exc:
            self.set_auth_message(
                f"Could not restore the saved sign-in. Sign in again. {exc}"
            )

    def open_account(self, user_data, access_token, refresh_token, expires_in=None):
        email = user_data.get("email")
        user_id = user_data.get("id")
        if not isinstance(email, str) or not email or not isinstance(user_id, str):
            raise SupabaseAuthError("Supabase did not return a valid account.")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise SupabaseAuthError(
                "Supabase did not return a refresh token, so this sign-in "
                "cannot be saved on this device."
            )
        profile = self.auth_client.get_profile(user_id, access_token)
        if self.session_store is None:
            raise SupabaseAuthError(
                "Could not securely save this sign-in on this device. "
                + self.session_store_error
            )
        access_level = profile["access_level"]
        device_ids = profile["device_ids"]
        unknown_devices = set(device_ids) - set(DEVICES)
        if unknown_devices:
            raise SupabaseAuthError(
                "Unknown device assignment(s): "
                + ", ".join(sorted(unknown_devices))
                + ". Update the profile to use a listed device ID."
            )
        try:
            self.session_store.save_refresh_token(refresh_token)
        except (OSError, SupabaseAuthError) as exc:
            raise SupabaseAuthError(
                f"Signed in, but could not securely save this device's session: {exc}"
            ) from exc
        private_key = None
        self.chat_setup_error = ""
        try:
            private_key = self.session_store.load_chat_private_key(user_id)
            if private_key is None:
                new_private_key, _ = generate_identity()
                self.session_store.save_chat_private_key(user_id, new_private_key)
                private_key = new_private_key
            public_key = public_key_for_private(private_key)
            self.auth_client.set_chat_public_key(public_key, access_token)
            self.chat_available = True
        except (SupabaseAuthError, ChatCryptoError) as exc:
            self.chat_setup_error = str(exc)
            self.chat_available = False
        self.user = email
        self.user_id = user_id
        self.access_level = access_level
        self.assigned_device_ids = device_ids
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.chat_private_key = private_key
        self.pairing_code = profile["pairing_code"]
        self.matrix_user_id = profile["matrix_user_id"]
        self.set_auth_message("")
        self.schedule_token_refresh(expires_in)
        self.enter_app()

    def schedule_token_refresh(self, expires_in=None):
        if (
            isinstance(expires_in, (int, float))
            and not isinstance(expires_in, bool)
            and expires_in > 0
        ):
            margin = min(300, max(5, expires_in * 0.1))
            seconds = max(10, expires_in - margin)
        else:
            seconds = 45 * 60
        self.refresh_timer.start(int(seconds * 1000))

    def refresh_access_token(self):
        if not self.refresh_token or self.auth_client is None:
            return
        try:
            result = self.auth_client.refresh_session(self.refresh_token)
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")
            user_data = result.get("user")
            if not isinstance(access_token, str) or not access_token:
                raise SupabaseAuthError("Supabase did not return a renewed access token.")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise SupabaseAuthError("Supabase did not return a renewed refresh token.")
            if not isinstance(user_data, dict) or user_data.get("id") != self.user_id:
                raise SupabaseAuthError("Supabase returned a different account during refresh.")
        except SupabaseAuthError as exc:
            self.set_pairing_message(f"Session refresh failed: {exc}", True)
            self.refresh_timer.start(60_000)
            return

        self.access_token = access_token
        self.refresh_token = refresh_token
        try:
            if self.session_store is None:
                raise SupabaseAuthError("Secure session storage is unavailable.")
            self.session_store.save_refresh_token(refresh_token)
        except (OSError, SupabaseAuthError) as exc:
            self.set_pairing_message(
                f"Session renewed, but the saved session could not be updated: {exc}",
                True,
            )
        self.schedule_token_refresh(result.get("expires_in"))

    def build_main(self):
        self.main = QWidget(); h = QHBoxLayout(self.main); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        self.side = Sidebar(); self.side.setFixedWidth(250)
        s = QVBoxLayout(self.side); s.setContentsMargins(20, 32, 20, 24); s.setSpacing(6)
        s.addWidget(text("Gleek", 20, QFont.Weight.DemiBold)); s.addSpacing(30)
        self.tabs = FadeStack()
        self.dash, self.devs = self.page_dash(), self.page_devices()
        self.pair, self.sets = self.page_pairing(), self.page_settings()
        for pg in (self.dash, self.devs, self.pair, self.sets): self.tabs.addWidget(pg)
        self.navs = []
        for name, pg in (("Dashboard", self.dash), ("Devices", self.devs),
                         ("Pairing", self.pair), ("Settings", self.sets)):
            b = GlowButton(name, "nav"); b.clicked.connect(lambda _, b=b, pg=pg: self.nav(b, pg))
            s.addWidget(b); self.navs.append(b)
        s.addStretch()
        me = QHBoxLayout(); me.setSpacing(12)
        self.avatar_slot = QHBoxLayout(); me.addLayout(self.avatar_slot)
        who = QVBoxLayout(); who.setSpacing(0)
        self.who_name, self.who_role = text("", 14, QFont.Weight.DemiBold), text("", 12, color=MUTED)
        who.addWidget(self.who_name); who.addWidget(self.who_role); me.addLayout(who); me.addStretch()
        s.addLayout(me); s.addSpacing(10)
        out = GlowButton("Sign out"); out.clicked.connect(self.logout); s.addWidget(out)
        h.addWidget(self.side); h.addWidget(self.tabs); self.root.addWidget(self.main)

    def nav(self, btn, page):
        self.prefs.setValue("last_tab", self.navs.index(btn))
        for b in self.navs: b.set_active(b is btn)
        self.side.goto(btn); self.tabs.fade_to(page)
        if page is self.dash: QTimer.singleShot(300, self.count_up)

    def page_dash(self):
        pg = QWidget(); l = QVBoxLayout(pg); l.setContentsMargins(48, 48, 48, 40); l.setSpacing(6)
        self.dash_title = text("", 32, QFont.Weight.DemiBold)
        self.dash_sub = text("", 15, color=MUTED)
        l.addWidget(self.dash_title); l.addWidget(self.dash_sub); l.addSpacing(26)
        row = QHBoxLayout(); row.setSpacing(18)
        self.st_total, self.st_online = StatCard("Devices you manage"), StatCard("Online right now")
        self.st_role = StatCard("Access level")
        for c in (self.st_total, self.st_online, self.st_role): row.addWidget(c)
        l.addLayout(row); l.addSpacing(18)
        card = Card(16, 0.8); cl = QHBoxLayout(card); cl.setContentsMargins(26, 22, 26, 22)
        tx = QVBoxLayout(); tx.setSpacing(2)
        tx.addWidget(text("Ready to start a session?", 16, QFont.Weight.DemiBold))
        tx.addWidget(text("Browse devices assigned to your access level.", 14, color=MUTED))
        go = GlowButton("Open devices", "primary"); go.setFixedWidth(160)
        go.clicked.connect(lambda: self.nav(self.navs[1], self.devs))
        cl.addLayout(tx); cl.addStretch(); cl.addWidget(go); l.addWidget(card); l.addStretch()
        return pg

    def page_devices(self):
        pg = QWidget(); l = QVBoxLayout(pg); l.setContentsMargins(48, 48, 48, 40); l.setSpacing(6)
        l.addWidget(text("Devices", 32, QFont.Weight.DemiBold))
        l.addWidget(text("Devices available to your access level. Connect is a demo.", 15, color=MUTED)); l.addSpacing(22)
        self.dev_list = QVBoxLayout(); self.dev_list.setSpacing(12); l.addLayout(self.dev_list); l.addStretch()
        return pg

    def page_settings(self):
        pg = QWidget(); outer = QVBoxLayout(pg)
        outer.setContentsMargins(48, 38, 48, 28)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea>QWidget>QWidget{background:transparent;}"
            "QScrollBar:vertical{background:#0E141B;width:8px;margin:4px;}"
            "QScrollBar::handle:vertical{background:#35485C;min-height:24px;border-radius:4px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
        )
        content = QWidget(); layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 12, 0); layout.setSpacing(10)
        layout.addWidget(text("Settings", 32, QFont.Weight.DemiBold))
        layout.addWidget(text("Your account and preferences on this machine.", 15, color=MUTED))
        layout.addSpacing(8)
        account_card = Card(16, 0.8)
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(26, 22, 26, 22)
        account_layout.setSpacing(4)
        self.set_user = text("", 16, QFont.Weight.DemiBold)
        self.set_role = text("", 14, color=MUTED)
        account_layout.addWidget(self.set_user)
        account_layout.addWidget(self.set_role)
        layout.addWidget(account_card)
        layout.addSpacing(6)
        layout.addWidget(text("Preferences", 16, QFont.Weight.DemiBold))
        self.pref_btns = {}
        self.pref_status = text("", 12, color=MUTED)
        self.pref_status.setWordWrap(True)
        for key, title, description, default in PREFS:
            row = Card(14, 0.65)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(20, 12, 14, 12)
            description_layout = QVBoxLayout()
            description_layout.setSpacing(1)
            description_layout.addWidget(text(title, 14, QFont.Weight.DemiBold))
            description_layout.addWidget(text(description, 12, color=MUTED))
            button = GlowButton("Off")
            button.setFixedSize(70, 36)
            self._style_pref(button, self.pref(key, default))
            button.clicked.connect(
                lambda _checked=False, key=key, default=default:
                self.set_pref(key, not self.pref(key, default))
            )
            self.pref_btns[key] = button
            row_layout.addLayout(description_layout)
            row_layout.addStretch()
            row_layout.addWidget(button)
            layout.addWidget(row)
        layout.addWidget(self.pref_status)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return pg

    def pref(self, key, default):
        return self.prefs.value(key, default, type=bool)

    @staticmethod
    def _style_pref(button, enabled):
        button.setText("On" if enabled else "Off")
        button.kind = "primary" if enabled else "secondary"
        button.glow_color = "#FFFFFF" if enabled else ACCENT
        button.update()

    def set_pref(self, key, enabled):
        if key == "autostart":
            try:
                set_autostart(enabled)
            except OSError as exc:
                self.pref_status.setText(f"Could not update Windows startup setting: {exc}")
                self.pref_status.setStyleSheet(f"color:{ERR};")
                return
        self.prefs.setValue(key, enabled)
        self.prefs.sync()
        if self.prefs.status() != QSettings.Status.NoError:
            self.pref_status.setText("Could not save this preference in Windows settings.")
            self.pref_status.setStyleSheet(f"color:{ERR};")
        else:
            self.pref_status.setText("")
        if key == "low_power":
            self.stage.set_low_power(enabled)
        button = self.pref_btns.get(key)
        if button is not None:
            self._style_pref(button, enabled)

    def page_pairing(self):
        pg = QWidget()
        page_layout = QVBoxLayout(pg)
        page_layout.setContentsMargins(48, 38, 48, 28)
        page_layout.setSpacing(6)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea>QWidget>QWidget{background:transparent;}"
            "QScrollBar:vertical{background:#0E141B;width:8px;margin:4px;}"
            "QScrollBar::handle:vertical{background:#35485C;min-height:24px;border-radius:4px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
        )
        content = QWidget(); l = QVBoxLayout(content)
        l.setContentsMargins(0, 0, 12, 0); l.setSpacing(8)
        l.addWidget(text("Pairing", 32, QFont.Weight.DemiBold))
        subtitle = text(
            "Pair with another Gleek user and chat here without creating a Matrix account. "
            "The recipient must approve pairing before chat is available.",
            14, color=MUTED,
        )
        subtitle.setWordWrap(True); l.addWidget(subtitle); l.addSpacing(8)
        self.chat_setup_notice = text("", 12, color=MUTED)
        self.chat_setup_notice.setWordWrap(True)
        l.addWidget(self.chat_setup_notice)

        code_card = Card(16, 0.8); code_layout = QHBoxLayout(code_card)
        code_layout.setContentsMargins(22, 16, 18, 16); code_layout.setSpacing(14)
        code_copy = QVBoxLayout(); code_copy.setSpacing(2)
        code_copy.addWidget(text("Your pairing code", 13, color=MUTED))
        self.pairing_code_label = text("", 22, QFont.Weight.DemiBold)
        self.pairing_code_label.setStyleSheet(f"color:{ACCENT}; letter-spacing:2px;")
        code_copy.addWidget(self.pairing_code_label)
        code_layout.addLayout(code_copy); code_layout.addStretch()
        copy_button = GlowButton("Copy code")
        copy_button.setFixedWidth(120)
        copy_button.clicked.connect(self.copy_pairing_code)
        code_layout.addWidget(copy_button); l.addWidget(code_card)

        request_card = Card(16, 0.8); request_layout = QVBoxLayout(request_card)
        request_layout.setContentsMargins(22, 16, 22, 16); request_layout.setSpacing(10)
        request_layout.addWidget(text("Request pairing", 16, QFont.Weight.DemiBold))
        request_row = QHBoxLayout(); request_row.setSpacing(12)
        self.pairing_code_input = AnimatedInput("Enter their 12-character code")
        self.pairing_code_input.setMaxLength(12)
        self.pairing_code_input.setFixedHeight(44)
        self.pairing_code_input.returnPressed.connect(self.send_pairing_request)
        request_row.addWidget(self.pairing_code_input)
        send_button = GlowButton("Send request", "primary")
        send_button.setFixedWidth(145)
        send_button.clicked.connect(self.send_pairing_request)
        request_row.addWidget(send_button)
        request_layout.addLayout(request_row)
        self.pairing_message = text("", 12, color=MUTED)
        self.pairing_message.setWordWrap(True)
        request_layout.addWidget(self.pairing_message)
        l.addWidget(request_card)

        matrix_card = Card(16, 0.8); matrix_layout = QVBoxLayout(matrix_card)
        matrix_layout.setContentsMargins(22, 16, 22, 16); matrix_layout.setSpacing(8)
        matrix_layout.addWidget(text("Optional Element profile", 16, QFont.Weight.DemiBold))
        matrix_help = text(
            "Gleek's in-app chat does not use Matrix. If you also use Element, you can "
            "optionally save your Matrix ID here for paired accounts.",
            13, color=MUTED,
        )
        matrix_help.setWordWrap(True); matrix_layout.addWidget(matrix_help)
        matrix_row = QHBoxLayout(); matrix_row.setSpacing(12)
        self.matrix_id_input = AnimatedInput("@username:matrix.org")
        self.matrix_id_input.setFixedHeight(44)
        matrix_row.addWidget(self.matrix_id_input)
        save_matrix_id = GlowButton("Save optional ID", "primary")
        save_matrix_id.setFixedWidth(150)
        save_matrix_id.clicked.connect(self.save_matrix_id)
        matrix_row.addWidget(save_matrix_id)
        matrix_layout.addLayout(matrix_row)
        self.matrix_status = text("", 12, color=MUTED)
        self.matrix_status.setWordWrap(True); matrix_layout.addWidget(self.matrix_status)
        l.addWidget(matrix_card)

        self.incoming_list = self._pairing_section(l, "Requests for you")
        self.outgoing_list = self._pairing_section(l, "Requests you sent")
        self.paired_list = self._pairing_section(l, "Paired accounts — chat in Gleek")
        l.addStretch()
        scroll.setWidget(content); page_layout.addWidget(scroll)
        return pg

    @staticmethod
    def _pairing_section(layout, title):
        layout.addWidget(text(title, 16, QFont.Weight.DemiBold))
        rows = QVBoxLayout(); rows.setSpacing(8)
        layout.addLayout(rows)
        return rows

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                Portal._clear_layout(item.layout())

    def copy_pairing_code(self):
        QApplication.clipboard().setText(self.pairing_code)
        self.set_pairing_message("Pairing code copied.", False)

    def set_pairing_message(self, message, is_error=False):
        self.pairing_message.setText(message)
        self.pairing_message.setStyleSheet(f"color:{ERR if is_error else MUTED};")

    def send_pairing_request(self):
        code = self.pairing_code_input.text().strip()
        try:
            self.auth_client.request_pairing(code, self.access_token)
        except SupabaseAuthError as exc:
            self.set_pairing_message(str(exc), True)
            self.pairing_code_input.error = True
            return
        self.pairing_code_input.clear()
        self.set_pairing_message("Request sent. The other person must approve it.")
        self.refresh_pairing_state()

    def refresh_pairing_state(self):
        if not self.access_token:
            return
        try:
            self.auth_client.update_presence(self.access_token)
            state = self.auth_client.get_pairing_state(self.access_token)
        except SupabaseAuthError as exc:
            self.set_pairing_message(str(exc), True)
            return
        pending_count = len(state["requests"])
        self.navs[2].setText(
            f"Pairing ({pending_count})" if pending_count else "Pairing"
        )
        incoming_ids = {
            entry["id"] for entry in state["requests"]
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
        if incoming_ids - self._known_pairing_requests:
            self.set_pairing_message("A new pairing request is waiting for your approval.")
            if self.pref("notify", True) and self.tray is not None:
                self.tray.showMessage(
                    "Gleek",
                    "New pairing request waiting for your approval.",
                    QSystemTrayIcon.MessageIcon.Information,
                    6000,
                )
        self._known_pairing_requests = incoming_ids
        self._show_pairing_rows(self.incoming_list, state["requests"], "incoming")
        self._show_pairing_rows(self.outgoing_list, state["outgoing"], "outgoing")
        self._show_pairing_rows(self.paired_list, state["pairings"], "paired")

    def _show_pairing_rows(self, layout, entries, kind):
        self._clear_layout(layout)
        if not entries:
            labels = {
                "incoming": "No one has requested to pair with you.",
                "outgoing": "No outgoing requests.",
                "paired": "No accounts are paired yet.",
            }
            layout.addWidget(text(labels[kind], 13, color=MUTED))
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            account = entry.get("email")
            if not isinstance(account, str) or not account:
                account = "Account " + str(entry.get("user_id", ""))[:8]
            row = Card(14, 0.65); row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(18, 8, 12, 8); row_layout.setSpacing(12)
            row_layout.addWidget(text(account, 14, QFont.Weight.DemiBold))
            row_layout.addStretch()
            if kind == "incoming":
                request_id = entry.get("id")
                approve = GlowButton("Approve", "primary")
                approve.setFixedSize(100, 36)
                approve.clicked.connect(
                    lambda _, request_id=request_id: self.respond_to_pairing(request_id, True)
                )
                deny = GlowButton("Decline")
                deny.setFixedSize(100, 36)
                deny.clicked.connect(
                    lambda _, request_id=request_id: self.respond_to_pairing(request_id, False)
                )
                row_layout.addWidget(approve); row_layout.addWidget(deny)
            elif kind == "paired":
                peer_id = entry.get("user_id")
                online = entry.get("online") is True
                row_layout.addWidget(StatusDot("online" if online else "offline"))
                row_layout.addWidget(
                    text(
                        "Online" if online else "Offline",
                        12,
                        color=ACCENT if online else MUTED,
                    )
                )
                last_seen = entry.get("last_seen")
                if isinstance(last_seen, str) and last_seen:
                    row_layout.addWidget(
                        text(
                            f"Last seen {last_seen[:16].replace('T', ' ')} UTC",
                            11,
                            color=MUTED,
                        )
                    )
                matrix_user_id = entry.get("matrix_user_id")
                chat_public_key = entry.get("chat_public_key")
                chat_button = GlowButton("Chat", "primary")
                chat_button.setFixedSize(84, 36)
                chat_button.setEnabled(
                    isinstance(peer_id, str)
                    and self.chat_private_key is not None
                    and isinstance(chat_public_key, str)
                    and bool(chat_public_key)
                )
                if not chat_button.isEnabled():
                    chat_button.setToolTip(
                        self.chat_setup_error
                        or "This account must update Gleek and sign in to enable encrypted chat."
                    )
                chat_button.clicked.connect(
                    lambda _, peer_id=peer_id, account=account,
                    chat_public_key=chat_public_key:
                    self.open_chat(peer_id, account, chat_public_key)
                )
                message_button = GlowButton("Open Element", "primary")
                message_button.setFixedWidth(120)
                message_button.setFixedHeight(36)
                message_button.setEnabled(
                    isinstance(matrix_user_id, str) and bool(matrix_user_id)
                )
                if not message_button.isEnabled():
                    message_button.setToolTip(
                        "This account needs to save its Matrix ID first."
                    )
                message_button.clicked.connect(
                    lambda _, matrix_user_id=matrix_user_id, account=account:
                    self.open_element_chat(matrix_user_id, account)
                )
                copy_id = GlowButton("Copy ID")
                copy_id.setFixedSize(84, 36)
                copy_id.setEnabled(isinstance(matrix_user_id, str) and bool(matrix_user_id))
                copy_id.clicked.connect(
                    lambda _, matrix_user_id=matrix_user_id:
                    self.copy_matrix_id(matrix_user_id)
                )
                revoke = GlowButton("Revoke")
                revoke.setFixedSize(100, 36)
                revoke.clicked.connect(
                    lambda _, peer_id=peer_id: self.revoke_pairing(peer_id)
                )
                row_layout.addWidget(chat_button)
                row_layout.addWidget(copy_id)
                row_layout.addWidget(message_button); row_layout.addWidget(revoke)
            else:
                row_layout.addWidget(text("Waiting for approval", 12, color=MUTED))
            layout.addWidget(row)

    def open_chat(self, peer_id, account, peer_public_key):
        if not isinstance(peer_id, str) or not isinstance(peer_public_key, str):
            self.set_pairing_message("This paired account has no chat encryption key yet.", True)
            return
        if self.chat_private_key is None:
            self.set_pairing_message(
                self.chat_setup_error or "Encrypted chat is not set up on this device.",
                True,
            )
            return
        if not self.chat_available:
            try:
                self.auth_client.set_chat_public_key(
                    public_key_for_private(self.chat_private_key),
                    self.access_token,
                )
                self.chat_available = True
                self.chat_setup_error = ""
            except (SupabaseAuthError, ChatCryptoError) as exc:
                self.chat_setup_error = str(exc)
                self.chat_setup_notice.setText(
                    f"Encrypted chat is unavailable: {self.chat_setup_error}"
                )
                self.chat_setup_notice.setStyleSheet(f"color:{ERR};")
                self.set_pairing_message(self.chat_setup_error, True)
                return
        dialog = self.chat_dialogs.get(peer_id)
        if dialog is not None:
            try:
                dialog.raise_()
                dialog.activateWindow()
                return
            except RuntimeError:
                self.chat_dialogs.pop(peer_id, None)
        dialog = ChatDialog(self, peer_id, account, peer_public_key)
        self.chat_dialogs[peer_id] = dialog
        dialog.finished.connect(lambda _result, peer_id=peer_id: self.chat_dialogs.pop(peer_id, None))
        dialog.show()

    def save_matrix_id(self):
        matrix_user_id = self.matrix_id_input.text().strip() or None
        try:
            self.auth_client.set_matrix_user_id(
                matrix_user_id, self.access_token
            )
        except SupabaseAuthError as exc:
            self.matrix_status.setText(str(exc))
            self.matrix_status.setStyleSheet(f"color:{ERR};")
            self.matrix_id_input.error = True
            return
        self.matrix_user_id = matrix_user_id
        self.matrix_status.setText(
            "Matrix ID saved. It will be visible to paired accounts."
            if matrix_user_id else "Matrix ID removed from your profile."
        )
        self.matrix_status.setStyleSheet(f"color:{MUTED};")
        self.refresh_pairing_state()

    def open_element_chat(self, matrix_user_id, account):
        if not isinstance(matrix_user_id, str) or not re.fullmatch(
            r"@[A-Za-z0-9._=/-]+:[A-Za-z0-9.-]+(?::[0-9]{1,5})?",
            matrix_user_id,
        ):
            self.set_pairing_message(
                f"{account} has not saved a valid Matrix ID.", True
            )
            return
        opened = QDesktopServices.openUrl(
            QUrl(f"https://matrix.to/#/{matrix_user_id}")
        )
        if opened:
            self.set_pairing_message(
                f"Opened the Matrix profile for {account}. In Element, verify their "
                "devices before sharing sensitive information."
            )
        else:
            QApplication.clipboard().setText(matrix_user_id)
            self.set_pairing_message(
                f"Could not open a browser, so {matrix_user_id} was copied. "
                "Paste it into Element's search to start a chat.",
                True,
            )

    def copy_matrix_id(self, matrix_user_id):
        if isinstance(matrix_user_id, str) and matrix_user_id:
            QApplication.clipboard().setText(matrix_user_id)
            self.set_pairing_message("Matrix ID copied.")

    def respond_to_pairing(self, request_id, accept):
        try:
            self.auth_client.respond_to_pairing(request_id, accept, self.access_token)
        except SupabaseAuthError as exc:
            self.set_pairing_message(str(exc), True)
            return
        self.set_pairing_message(
            "Account paired. You can see recent app presence and open their Matrix profile."
            if accept else "Pairing request declined."
        )
        self.refresh_pairing_state()

    def revoke_pairing(self, peer_id):
        try:
            self.auth_client.revoke_pairing(peer_id, self.access_token)
        except SupabaseAuthError as exc:
            self.set_pairing_message(str(exc), True)
            return
        self.set_pairing_message("Pairing revoked.")
        self.refresh_pairing_state()

    def enter_app(self):
        display_name = self.user.split("@", 1)[0]
        role = self.access_level.replace("_", " ").title()
        hr = time.localtime().tm_hour
        hello = "Good morning" if hr < 12 else "Good afternoon" if hr < 18 else "Good evening"
        self.dash_title.setText(f"{hello}, {display_name.capitalize()}")
        self.dash_sub.setText("Here's where your devices stand.")
        self.who_name.setText(display_name.capitalize()); self.who_role.setText(role)
        self.set_user.setText(self.user); self.set_role.setText(f"{role} access")
        self.st_role.value.setText(role)
        while self.avatar_slot.count():
            it = self.avatar_slot.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        self.avatar_slot.addWidget(Avatar(display_name))
        self.pairing_code_label.setText(self.pairing_code.upper())
        self.matrix_id_input.setText(self.matrix_user_id or "")
        self.matrix_status.setText(
            "Matrix ID saved." if self.matrix_user_id else
            "Optional. Gleek chat works without a Matrix account."
        )
        self.chat_setup_notice.setText(
            f"Encrypted chat setup issue: {self.chat_setup_error}"
            if self.chat_setup_error else
            "In-app chat encrypts messages on this device; Matrix is not required."
        )
        self.chat_setup_notice.setStyleSheet(
            f"color:{ERR if self.chat_setup_error else MUTED};"
        )
        self.fill_devices()
        index = self.prefs.value("last_tab", 0, type=int)
        if not 0 <= index < len(self.navs):
            index = 0
        self.tabs.setCurrentIndex(index)
        for button in self.navs:
            button.set_active(button is self.navs[index])
        self.root.fade_to(self.main)
        QTimer.singleShot(60, lambda: self.side.goto(self.navs[index], False))
        QTimer.singleShot(650, self.count_up)
        self.refresh_pairing_state()
        self.pairing_timer.start()

    def count_up(self):
        self.st_total.count_to(self.n_total); self.st_online.count_to(self.n_online)

    def fill_devices(self):
        while self.dev_list.count():
            it = self.dev_list.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        if self.access_level == "owner":
            ids = list(DEVICES)
        elif self.access_level == "admin":
            ids = self.assigned_device_ids
        else:
            ids = []
        self.n_total = self.n_online = 0
        self.st_total.value.setText("0"); self.st_online.value.setText("0")
        if not ids:
            self.dev_list.addWidget(text("No devices are assigned to this account.", 14, color=MUTED))
            return
        self.n_total = len(ids)
        self.n_online = sum(DEVICES[device_id][1] == "online" for device_id in ids)
        for device_id in ids:
            ip, state = DEVICES[device_id]
            row = Card(14, 0.8); row.setFixedHeight(68)
            layout = QHBoxLayout(row); layout.setContentsMargins(24, 0, 18, 0); layout.setSpacing(14)
            layout.addWidget(StatusDot(state))
            layout.addWidget(text(device_id, 15, QFont.Weight.DemiBold))
            layout.addWidget(text(state.capitalize(), 13, color=MUTED)); layout.addStretch()
            layout.addWidget(text(ip, 13, color=MUTED)); layout.addSpacing(10)
            button = GlowButton("Demo connect")
            button.setFixedSize(116, 38)
            button.setEnabled(state != "offline")
            button.clicked.connect(lambda _, btn=button: self.connect_device(btn))
            layout.addWidget(button)
            self.dev_list.addWidget(row)

    def connect_device(self, btn):      # stand-in: plug your real connection logic in here
        btn.setText("Connecting…"); btn.setEnabled(False)
        def done():
            try: btn.setText("Connected"); btn.setEnabled(True)
            except RuntimeError: pass
        QTimer.singleShot(1400, done)

    def logout(self):
        try:
            if self.session_store is not None:
                self.session_store.clear()
        except SupabaseAuthError as exc:
            self.set_pairing_message(
                f"Could not sign out because the saved session could not be removed: {exc}",
                True,
            )
            self.nav(self.navs[2], self.pair)
            return
        try:
            if self.access_token:
                self.auth_client.clear_presence(self.access_token)
        except SupabaseAuthError as exc:
            self.set_pairing_message(
                f"Signed out locally; online status will expire shortly. {exc}", True
            )
        self.pairing_timer.stop()
        self.refresh_timer.stop()
        self.user = self.user_id = self.access_level = None
        self.access_token = None
        self.refresh_token = None
        self.chat_private_key = None
        self.chat_available = False
        for dialog in list(self.chat_dialogs.values()):
            dialog.close()
        self.chat_dialogs.clear()
        self.matrix_user_id = None
        self._known_pairing_requests.clear()
        self.assigned_device_ids = []
        self.email_in.clear(); self.pass_in.clear(); self.confirm_in.clear()
        self.root.fade_to(self.login_page)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    f = QFont(); f.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", "Arial"])
    f.setPixelSize(14); app.setFont(f)
    app.setStyleSheet("QLabel{background:transparent;}")
    w = Portal(); w.show()
    sys.exit(app.exec())