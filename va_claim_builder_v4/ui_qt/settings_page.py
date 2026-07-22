from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.settings import AISettings, SettingsManager


class SettingsPage(QWidget):
    settings_saved = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = SettingsManager()

        heading = QLabel("AI & Privacy Settings")
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        description = QLabel(
            "API keys are encrypted in the VA Claim Builder application-data folder and are never stored in a project."
        )
        description.setWordWrap(True)

        self.provider = QComboBox()
        self.provider.addItems(["openai", "xai"])
        self.fallback = QComboBox()
        self.fallback.addItems(["", "openai", "xai"])
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setPlaceholderText("OpenAI API key")
        self.xai_key = QLineEdit()
        self.xai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.xai_key.setPlaceholderText("xAI API key")
        self.openai_model = QLineEdit()
        self.xai_model = QLineEdit()
        self.local_only = QCheckBox("Disable all cloud AI calls")
        self.redact = QCheckBox("Redact identifiers before cloud AI calls")

        provider_box = QGroupBox("Providers")
        provider_form = QFormLayout(provider_box)
        provider_form.addRow("Primary provider", self.provider)
        provider_form.addRow("Fallback provider", self.fallback)
        provider_form.addRow("OpenAI API key", self.openai_key)
        provider_form.addRow("OpenAI model", self.openai_model)
        provider_form.addRow("xAI API key", self.xai_key)
        provider_form.addRow("xAI model", self.xai_model)

        privacy_box = QGroupBox("Privacy")
        privacy_layout = QVBoxLayout(privacy_box)
        privacy_layout.addWidget(self.local_only)
        privacy_layout.addWidget(self.redact)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.save)
        clear_button = QPushButton("Clear API Keys")
        clear_button.clicked.connect(self.clear_keys)
        show_button = QPushButton("Show/Hide Keys")
        show_button.clicked.connect(self.toggle_key_visibility)

        button_row = QHBoxLayout()
        button_row.addWidget(self.save_button)
        button_row.addWidget(clear_button)
        button_row.addWidget(show_button)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addWidget(provider_box)
        layout.addWidget(privacy_box)
        layout.addLayout(button_row)
        layout.addStretch()
        self.load()

    def load(self) -> None:
        settings = self.manager.load_ai_settings()
        self.provider.setCurrentText(settings.provider)
        self.fallback.setCurrentText(settings.fallback_provider)
        self.openai_key.setText(settings.openai_api_key)
        self.xai_key.setText(settings.xai_api_key)
        self.openai_model.setText(settings.model_openai)
        self.xai_model.setText(settings.model_xai)
        self.local_only.setChecked(settings.local_only)
        self.redact.setChecked(settings.redact_before_cloud)

    def save(self) -> None:
        settings = AISettings(
            provider=self.provider.currentText(),
            fallback_provider=self.fallback.currentText(),
            openai_api_key=self.openai_key.text().strip(),
            xai_api_key=self.xai_key.text().strip(),
            local_only=self.local_only.isChecked(),
            redact_before_cloud=self.redact.isChecked(),
            model_openai=self.openai_model.text().strip() or "gpt-4o-mini",
            model_xai=self.xai_model.text().strip() or "grok-3-mini",
        )
        if settings.fallback_provider == settings.provider:
            settings.fallback_provider = ""
            self.fallback.setCurrentText("")
        self.manager.save_ai_settings(settings)
        self.manager.apply_to_environment(settings)
        self.settings_saved.emit()
        QMessageBox.information(self, "Settings saved", "AI and privacy settings were saved securely.")

    def clear_keys(self) -> None:
        self.manager.clear_api_keys()
        self.openai_key.clear()
        self.xai_key.clear()
        self.manager.apply_to_environment()
        QMessageBox.information(self, "Keys cleared", "Stored OpenAI and xAI API keys were removed.")

    def toggle_key_visibility(self) -> None:
        mode = self.openai_key.echoMode()
        new_mode = QLineEdit.EchoMode.Normal if mode == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password
        self.openai_key.setEchoMode(new_mode)
        self.xai_key.setEchoMode(new_mode)
