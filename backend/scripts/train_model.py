#!/usr/bin/env python3
"""
RecoverAI – CLI Training Script.

Trains the GradientBoostingClassifier on seeded payment data,
prints actual evaluation metrics, saves model artifacts.

Usage:
    cd backend
    python3 scripts/train_model.py
"""
import logging
import sys
from pathlib import Path

# Make app importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.config import get_settings
from app.ml.train import run_training_and_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

console = Console()


def main() -> None:
    settings = get_settings()
    artifacts_dir = settings.ml_artifacts_dir

    console.print(Panel.fit(
        "[bold cyan]RecoverAI — ML Training Pipeline[/bold cyan]\n"
        f"Database:     {settings.database_url}\n"
        f"Artifacts:    {artifacts_dir}",
        border_style="cyan",
    ))

    console.print("\n[yellow]Starting training...[/yellow]\n")

    try:
        result = run_training_and_store(settings.database_url, artifacts_dir)
    except Exception as e:
        console.print(f"[bold red]Training failed:[/bold red] {e}")
        sys.exit(1)

    # ── Dataset stats ─────────────────────────────────────────────────────────
    ds_table = Table(title="Dataset", show_header=True, header_style="bold magenta")
    ds_table.add_column("Metric", style="cyan")
    ds_table.add_column("Value", justify="right")
    ds_table.add_row("Training samples",  f"{result.train_size:,}")
    ds_table.add_row("Test samples",      f"{result.test_size:,}")
    ds_table.add_row("Total samples",     f"{result.train_size + result.test_size:,}")
    ds_table.add_row("Positive rate",     f"{result.positive_rate:.2%}")
    ds_table.add_row("Model version",     result.model_version)
    console.print(ds_table)

    # ── Evaluation metrics ────────────────────────────────────────────────────
    metrics_table = Table(title="Evaluation Metrics (Test Set)", show_header=True, header_style="bold magenta")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", justify="right")

    def _color(val: float, good: float = 0.70) -> str:
        color = "green" if val >= good else ("yellow" if val >= 0.55 else "red")
        return f"[{color}]{val:.4f}[/{color}]"

    metrics_table.add_row("ROC-AUC",  _color(result.roc_auc, 0.70))
    metrics_table.add_row("Accuracy", _color(result.accuracy, 0.70))
    metrics_table.add_row("Precision",_color(result.precision, 0.65))
    metrics_table.add_row("Recall",   _color(result.recall, 0.55))
    console.print(metrics_table)

    # ── Confusion matrix ──────────────────────────────────────────────────────
    cm = result.confusion
    console.print("\n[bold]Confusion Matrix:[/bold]")
    console.print(f"               Predicted: 0    1")
    console.print(f"  Actual: 0       {cm[0][0]:>6}  {cm[0][1]:>6}")
    console.print(f"  Actual: 1       {cm[1][0]:>6}  {cm[1][1]:>6}")

    console.print("\n[bold]Classification Report:[/bold]")
    console.print(result.classification_rep)

    # ── Feature importances (top 10) ──────────────────────────────────────────
    fi_table = Table(title="Top 10 Feature Importances", show_header=True, header_style="bold magenta")
    fi_table.add_column("Rank", justify="right")
    fi_table.add_column("Feature", style="cyan")
    fi_table.add_column("Importance", justify="right")
    for i, fi in enumerate(result.feature_importances[:10], 1):
        fi_table.add_row(str(i), fi["feature"], f"{fi['importance']:.6f}")
    console.print(fi_table)

    # ── Artifacts ─────────────────────────────────────────────────────────────
    console.print(Panel.fit(
        f"[bold green]Training complete![/bold green]\n\n"
        f"Model artifact:    {result.model_path}\n"
        f"Encoder artifact:  {result.encoder_path}\n"
        f"Feature names:     {result.feature_names_path}\n\n"
        f"ROC-AUC: [bold]{result.roc_auc:.4f}[/bold]  "
        f"Accuracy: [bold]{result.accuracy:.4f}[/bold]  "
        f"Precision: [bold]{result.precision:.4f}[/bold]  "
        f"Recall: [bold]{result.recall:.4f}[/bold]",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
