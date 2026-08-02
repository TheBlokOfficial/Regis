from rich.console import Console
from rich.theme import Theme
import questionary
from questionary import Style

# Definicja minimalistycznego motywu barwnego dla Rich
custom_theme = Theme({
    "info": "dim white",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "header": "bold white"
})

console = Console(theme=custom_theme, highlight=False)

# Definicja wyciszonego motywu dla Questionary
custom_style = Style([
    ('qmark', 'fg:#808080 bold'),       # Znak zapytania
    ('question', 'bold'),               # Tekst pytania
    ('answer', 'fg:#d3d3d3 bold'),      # Wybrana odpowiedź
    ('pointer', 'fg:#ffffff bold'),     # Wskaźnik (strzałka)
    ('highlighted', 'fg:#ffffff bold'), # Podświetlona opcja
    ('selected', 'fg:#808080'),         # Zaznaczona opcja (w multi-select)
    ('separator', 'fg:#808080'),        # Separator
    ('instruction', 'fg:#808080'),      # Instrukcja (np. "użyj strzałek")
    ('text', ''),                       # Zwykły tekst
])
