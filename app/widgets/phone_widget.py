"""
Widget téléphone réutilisable avec sélecteur de pays
==================================================

Ce module fournit un widget téléphone standardisé pour toute l'application.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLineEdit
from PySide6.QtCore import Signal
from loguru import logger


class PhoneNumberWidget(QWidget):
    """Widget réutilisable pour les numéros de téléphone avec sélecteur de pays."""
    
    phone_changed = Signal(str)  # Signal émis quand le numéro change
    
    def __init__(self, initial_phone: str = "", placeholder: str = "Téléphone...", parent=None):
        super().__init__(parent)
        self.setup_ui(initial_phone, placeholder)
    
    def setup_ui(self, initial_phone: str, placeholder: str):
        """Configure l'interface du widget téléphone."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Sélecteur de pays
        self.country_combo = QComboBox()
        self.country_combo.setFixedWidth(100)
        self.country_combo.setStyleSheet("""
            QComboBox {
                background: transparent;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 2px 5px;
                font-size: 11px;
            }
        """)
        
        # Codes pays populaires
        countries = [
            ("🇫🇷 +33", "+33"),
            ("🇺🇸 +1", "+1"),
            ("🇬🇧 +44", "+44"),
            ("🇩🇪 +49", "+49"),
            ("🇪🇸 +34", "+34"),
            ("🇮🇹 +39", "+39"),
            ("🇨🇭 +41", "+41"),
            ("🇧🇪 +32", "+32"),
            ("🇳🇱 +31", "+31"),
            ("🇵🇹 +351", "+351"),
            ("🇨🇦 +1", "+1"),
            ("🇦🇺 +61", "+61"),
            ("🇯🇵 +81", "+81"),
            ("🇨🇳 +86", "+86"),
            ("🇮🇳 +91", "+91"),
            ("🇧🇷 +55", "+55"),
            ("🇦🇷 +54", "+54"),
            ("🇲🇽 +52", "+52"),
            ("🇿🇦 +27", "+27"),
            ("🇲🇦 +212", "+212"),
            ("🇹🇳 +216", "+216"),
            ("🇩🇿 +213", "+213"),
        ]
        
        for display, code in countries:
            self.country_combo.addItem(display, code)
        
        # Détecter le pays depuis le numéro initial
        if initial_phone:
            self.detect_country_from_phone(initial_phone)
        
        layout.addWidget(self.country_combo)
        
        # Champ numéro de téléphone
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText(placeholder)
        self.phone_edit.setMinimumWidth(150)  # Largeur minimale augmentée pour afficher les numéros complets
        self.phone_edit.setStyleSheet("""
            QLineEdit {
                background: transparent; 
                border: 1px solid #555555; 
                border-radius: 3px; 
                padding: 3px 5px; 
                font-size: 12px;
                color: white;
            }
            QLineEdit:hover {
                border: 1px solid #4db8ff;
                background-color: rgba(77, 184, 255, 0.1);
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: rgba(77, 184, 255, 0.15);
            }
        """)
        
        # Extraire le numéro sans code pays pour l'affichage
        phone_number = self.extract_national_number(initial_phone)
        self.phone_edit.setText(phone_number)
        
        layout.addWidget(self.phone_edit)
        
        # Connecter les signaux
        self.country_combo.currentTextChanged.connect(self.on_phone_changed)
        self.phone_edit.textChanged.connect(self.on_phone_changed)
        self.phone_edit.editingFinished.connect(self.on_editing_finished)
    
    def detect_country_from_phone(self, phone: str):
        """Détecte le pays depuis un numéro international."""
        phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        
        if phone.startswith("+33") or phone.startswith("0033"):
            self.country_combo.setCurrentText("🇫🇷 +33")
        elif phone.startswith("+1") or phone.startswith("001"):
            self.country_combo.setCurrentText("🇺🇸 +1")
        elif phone.startswith("+44") or phone.startswith("0044"):
            self.country_combo.setCurrentText("🇬🇧 +44")
        elif phone.startswith("+49") or phone.startswith("0049"):
            self.country_combo.setCurrentText("🇩🇪 +49")
        # Ajouter d'autres détections selon les besoins
    
    def extract_national_number(self, phone: str) -> str:
        """Extrait le numéro national (sans code pays)."""
        if not phone:
            return ""
        
        phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        
        # Supprimer les codes pays connus
        if phone.startswith("+33") or phone.startswith("0033"):
            return phone.replace("+33", "").replace("0033", "")
        elif phone.startswith("+1") or phone.startswith("001"):
            return phone.replace("+1", "").replace("001", "")
        elif phone.startswith("+44") or phone.startswith("0044"):
            return phone.replace("+44", "").replace("0044", "")
        elif phone.startswith("+49") or phone.startswith("0049"):
            return phone.replace("+49", "").replace("0049", "")
        
        # Si pas de code pays détecté, retourner tel quel
        return phone
    
    def get_full_phone_number(self) -> str:
        """Retourne le numéro complet avec code pays."""
        country_code = self.country_combo.currentData()
        national_number = self.phone_edit.text().strip()
        
        if not national_number:
            return ""
        
        # Nettoyer le numéro national
        national_number = national_number.replace(" ", "").replace("-", "")
        
        return f"{country_code} {national_number}"
    
    def set_phone_number(self, phone: str):
        """Définit le numéro de téléphone complet."""
        self.detect_country_from_phone(phone)
        national_number = self.extract_national_number(phone)
        self.phone_edit.setText(national_number)
    
    def on_phone_changed(self):
        """Appelé quand le numéro ou le pays change."""
        full_number = self.get_full_phone_number()
        self.phone_changed.emit(full_number)
    
    def on_editing_finished(self):
        """Appelé quand l'édition est terminée."""
        # Format automatique du numéro
        national_number = self.phone_edit.text().strip().replace(" ", "").replace("-", "")
        
        if national_number and self.country_combo.currentData() == "+33":
            # Format français intelligent
            if len(national_number) == 9 and not national_number.startswith("0"):
                # Numéro de 9 chiffres sans 0 initial (ex: 123456789 -> 1 23 45 67 89)
                formatted = f"{national_number[0]} {national_number[1:3]} {national_number[3:5]} {national_number[5:7]} {national_number[7:9]}"
                self.phone_edit.setText(formatted)
            elif len(national_number) == 10:
                if national_number.startswith("0"):
                    # Numéro de 10 chiffres avec 0 initial (ex: 0123456789 -> 01 23 45 67 89)
                    formatted = f"{national_number[:2]} {national_number[2:4]} {national_number[4:6]} {national_number[6:8]} {national_number[8:10]}"
                    self.phone_edit.setText(formatted)
                else:
                    # Numéro de 10 chiffres sans 0 initial -> ERREUR, ajouter le 0
                    national_number = "0" + national_number[1:]  # Remplacer le 1er chiffre par 0
                    formatted = f"{national_number[:2]} {national_number[2:4]} {national_number[4:6]} {national_number[6:8]} {national_number[8:10]}"
                    self.phone_edit.setText(formatted)
            # Gérer le cas problématique comme "62 57 84 9" qui devient "0X 25 78 49" 
            elif len(national_number) < 9:
                # Laisser tel quel si trop court, pas de formatage
                pass
        
        self.on_phone_changed()


def create_phone_widget(initial_phone: str = "", placeholder: str = "Téléphone...", parent=None) -> PhoneNumberWidget:
    """
    Fonction utilitaire globale pour créer un widget téléphone avec sélecteur de pays.
    
    Args:
        initial_phone: Numéro de téléphone initial (ex: "+33 1 23 45 67 89")
        placeholder: Texte de placeholder pour le champ
        parent: Widget parent
    
    Returns:
        PhoneNumberWidget: Widget téléphone configuré
    
    Usage:
        # Dans n'importe quelle interface:
        from app.widgets.phone_widget import create_phone_widget
        
        phone_widget = create_phone_widget("+33 1 23 45 67 89", "Téléphone professionnel...", self)
        phone_widget.phone_changed.connect(self.on_phone_updated)
        layout.addWidget(phone_widget)
        
        # Pour récupérer le numéro complet:
        full_number = phone_widget.get_full_phone_number()
        
        # Pour définir un nouveau numéro:
        phone_widget.set_phone_number("+44 20 1234 5678")
    """
    return PhoneNumberWidget(initial_phone, placeholder, parent)
