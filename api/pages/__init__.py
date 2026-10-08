"""Admin/login page HTML, one module per page. Shared styles/nav in _shared."""
from api.pages.login import LOGIN_HTML
from api.pages.settings import settings_html
from api.pages.charts import charts_html
from api.pages.report import report_html
from api.pages.faq import faq_html
from api.pages.privacidade import privacidade_html

__all__ = ["LOGIN_HTML", "settings_html", "charts_html", "report_html",
           "faq_html", "privacidade_html"]
