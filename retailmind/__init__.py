"""RetailMind AI — universal, dynamic, AI-assisted business analytics.

This package contains the Phase 1 platform foundation:

* ``retailmind.config``   — application metadata and environment configuration
* ``retailmind.models``   — dashboard/page/component configuration models
* ``retailmind.schema``   — universal dataset profiling and semantic role detection
* ``retailmind.cleaning`` — transparent, reviewable data preparation
* ``retailmind.engine``   — automatic dashboard generation
* ``retailmind.render``   — component rendering (KPI cards, charts, tables)
* ``retailmind.filters``  — universal interactive filters
* ``retailmind.storage``  — session/local dashboard persistence and undo/redo
* ``retailmind.ui``       — Power BI-inspired layout and theming helpers
* ``retailmind.ai``       — NLP, chatbot, dashboard assistant, insights and RAG

The running application entry point remains ``dashboard.py`` at the project root.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
