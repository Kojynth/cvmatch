"""
Gestionnaire de styles réutilisable pour toute l'application
========================================================

Ce module centralise tous les styles pour garantir la cohérence visuelle.
"""

class StyleManager:
    """Gestionnaire centralisé des styles pour l'application."""
    
    # Couleurs principales
    COLORS = {
        'primary': '#0078d4',
        'success': '#28a745', 
        'danger': '#dc2626',
        'warning': '#ffc107',
        'info': '#17a2b8',
        'dark': '#2d2d2d',
        'light': '#f8f9fa',
        'border': '#555555',
        'focus': '#4db8ff',
        'text_dark': '#ffffff',
        'text_light': '#000000',
        'background_dark': '#3a3a3a',
        'background_light': '#ffffff'
    }
    
    @staticmethod
    def get_button_style(button_type: str = "primary", size: str = "normal") -> str:
        """
        Retourne le style CSS pour un bouton.
        
        Args:
            button_type: "primary", "success", "danger", "warning", "info"
            size: "small", "normal", "large"
        """
        colors = StyleManager.COLORS
        base_color = colors.get(button_type, colors['primary'])
        
        # Calculer couleur hover (plus sombre)
        hover_color = StyleManager._darken_color(base_color)
        
        padding = {
            'small': '6px 12px',
            'normal': '10px 20px', 
            'large': '14px 28px'
        }.get(size, '10px 20px')
        
        return f"""
            QPushButton {{
                background-color: {base_color};
                color: white;
                border: none;
                padding: {padding};
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {StyleManager._darken_color(hover_color)};
            }}
            QPushButton:disabled {{
                background-color: #666666;
                color: #999999;
            }}
        """
    
    @staticmethod
    def get_input_style(theme: str = "dark") -> str:
        """Retourne le style CSS pour les champs de saisie."""
        colors = StyleManager.COLORS
        
        if theme == "dark":
            bg_color = colors['background_dark']
            text_color = colors['text_dark']
            border_color = colors['border']
        else:
            bg_color = colors['background_light']
            text_color = colors['text_light']
            border_color = '#ced4da'
        
        return f"""
            QLineEdit, QTextEdit, QComboBox {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 8px;
                color: {text_color};
                font-size: 13px;
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
                border: 2px solid {colors['focus']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: 2px solid {text_color};
                width: 6px;
                height: 6px;
                border-top: none;
                border-left: none;
                margin-right: 5px;
            }}
        """
    
    @staticmethod
    def get_groupbox_style() -> str:
        """Retourne le style CSS pour les groupes/sections."""
        colors = StyleManager.COLORS
        return f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {colors['border']};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                color: {colors['focus']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }}
        """
    
    @staticmethod
    def get_section_header_style() -> str:
        """Retourne le style pour les en-têtes de section."""
        colors = StyleManager.COLORS
        return f"""
            QLabel {{
                color: {colors['focus']};
                font-size: 14px;
                font-weight: bold;
                padding: 5px 0px;
                border-bottom: 1px solid {colors['border']};
                margin-bottom: 10px;
            }}
        """
    
    @staticmethod
    def _darken_color(hex_color: str, factor: float = 0.8) -> str:
        """Assombrit une couleur hexadécimale."""
        # Supprimer le #
        hex_color = hex_color.lstrip('#')
        
        # Convertir en RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16) 
        b = int(hex_color[4:6], 16)
        
        # Assombrir
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
        
        # Reconvertir en hex
        return f"#{r:02x}{g:02x}{b:02x}"


def apply_button_style(button, button_type: str = "primary", size: str = "normal"):
    """Fonction utilitaire pour appliquer un style à un bouton."""
    button.setStyleSheet(StyleManager.get_button_style(button_type, size))


def apply_input_style(widget, theme: str = "dark"):
    """Fonction utilitaire pour appliquer un style aux champs de saisie."""
    widget.setStyleSheet(StyleManager.get_input_style(theme))


def apply_section_header_style(label):
    """Fonction utilitaire pour appliquer un style aux en-têtes de section."""
    label.setStyleSheet(StyleManager.get_section_header_style())
