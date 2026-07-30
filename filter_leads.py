from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import pandas as pd
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
from rich.table import Table

# Try to import our models, fallback to dict if not in path
try:
    from models.business import Business
except ImportError:
    Business = None

# ---------------------------------------------------------------------------
# Logging & Console
# ---------------------------------------------------------------------------
console = Console()
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console)]
)
logger = logging.getLogger("filter_leads")

# ---------------------------------------------------------------------------
# Data Models & Flattening
# ---------------------------------------------------------------------------

def flatten_business(data: Dict[str, Any]) -> Dict[str, Any]:
    """Flattens the nested Business JSON structure for CSV/Excel export."""
    # We follow the mapping defined in requirements.md
    addr = data.get("address", {})
    cont = data.get("contact", {})
    soc = data.get("social_media", {})
    info = data.get("business_info", {})
    rat = data.get("ratings", {})
    meta = data.get("metadata", {})

    flat = {
        "Business Name": data.get("business_name"),
        "Place ID": data.get("place_id"),
        "Google Maps URL": data.get("google_maps_url"),
        "Full Address": addr.get("full_address"),
        "Street": addr.get("street"),
        "City": addr.get("city"),
        "State": addr.get("state"),
        "Zip": addr.get("postal_code"),
        "Country": addr.get("country"),
        "Phone": cont.get("phone"),
        "Website": cont.get("website"),
        "Email": cont.get("email"),
        "Facebook": soc.get("facebook"),
        "Instagram": soc.get("instagram"),
        "Twitter": soc.get("twitter"),
        "LinkedIn": soc.get("linkedin"),
        "YouTube": soc.get("youtube"),
        "TikTok": soc.get("tiktok"),
        "Primary Category": info.get("category"),
        "All Categories": ", ".join(info.get("all_categories", [])),
        "Description": info.get("description"),
        "Rating": rat.get("average_rating"),
        "Reviews": rat.get("total_reviews"),
        "Query": meta.get("query"),
        "Scraped At": meta.get("scraped_at"),
    }
    return flat

# ---------------------------------------------------------------------------
# Filtration Engine & Rules
# ---------------------------------------------------------------------------

@dataclass
class FilterConfig:
    # Contact
    require_phone: bool = False
    require_website: bool = False
    require_email: bool = False
    
    # Quality
    min_rating: Optional[float] = None
    min_reviews: Optional[int] = None
    
    # Categories
    category_whitelist: List[str] = field(default_factory=list)
    category_blacklist: List[str] = field(default_factory=list)
    
    # Keywords
    keywords: List[str] = field(default_factory=list)
    
    # Social Media
    require_socials: List[str] = field(default_factory=list) # e.g. ["instagram", "facebook"]
    social_logic: str = "AND" # "AND" or "OR"
    
    # Global Logic
    global_logic: str = "AND" # "AND" or "OR"
    deduplicate: bool = True

class FilterRule:
    def evaluate(self, business: Dict[str, Any]) -> bool:
        raise NotImplementedError

class ContactRule(FilterRule):
    def __init__(self, phone: bool, website: bool, email: bool):
        self.phone = phone
        self.website = website
        self.email = email

    def evaluate(self, b: Dict[str, Any]) -> bool:
        cont = b.get("contact", {})
        results = []
        if self.phone: results.append(bool(cont.get("phone")))
        if self.website: results.append(bool(cont.get("website")))
        if self.email: results.append(bool(cont.get("email")))
        return all(results) if results else True

class QualityRule(FilterRule):
    def __init__(self, min_rating: Optional[float], min_reviews: Optional[int]):
        self.min_rating = min_rating
        self.min_reviews = min_reviews

    def evaluate(self, b: Dict[str, Any]) -> bool:
        rat = b.get("ratings", {})
        if self.min_rating is not None:
            val = rat.get("average_rating")
            if val is None or val < self.min_rating: return False
        if self.min_reviews is not None:
            val = rat.get("total_reviews")
            if val is None or val < self.min_reviews: return False
        return True

class CategoryRule(FilterRule):
    def __init__(self, whitelist: List[str], blacklist: List[str]):
        self.whitelist = [c.lower() for c in whitelist]
        self.blacklist = [c.lower() for c in blacklist]

    def evaluate(self, b: Dict[str, Any]) -> bool:
        info = b.get("business_info", {})
        cats = [c.lower() for c in ([info.get("category")] + info.get("all_categories", [])) if c]
        
        if self.whitelist:
            if not any(c in self.whitelist for c in cats):
                return False
        
        if self.blacklist:
            if any(c in self.blacklist for c in cats):
                return False
                
        return True

class KeywordRule(FilterRule):
    def __init__(self, keywords: List[str]):
        self.keywords = [k.lower() for k in keywords]

    def evaluate(self, b: Dict[str, Any]) -> bool:
        if not self.keywords: return True
        name = (b.get("business_name") or "").lower()
        desc = (b.get("business_info", {}).get("description") or "").lower()
        combined = f"{name} {desc}"
        return any(k in combined for k in self.keywords)

class SocialMediaRule(FilterRule):
    def __init__(self, platforms: List[str], logic: str = "AND"):
        self.platforms = [p.lower() for p in platforms]
        self.logic = logic

    def evaluate(self, b: Dict[str, Any]) -> bool:
        if not self.platforms: return True
        soc = b.get("social_media", {})
        results = [bool(soc.get(p)) for p in self.platforms]
        return all(results) if self.logic == "AND" else any(results)

class FilterEngine:
    def __init__(self, config: FilterConfig):
        self.config = config
        self.rules: List[FilterRule] = []
        self._setup_rules()
        self.seen_ids: Set[str] = set()

    def _setup_rules(self):
        if any([self.config.require_phone, self.config.require_website, self.config.require_email]):
            self.rules.append(ContactRule(self.config.require_phone, self.config.require_website, self.config.require_email))
        
        if self.config.min_rating is not None or self.config.min_reviews is not None:
            self.rules.append(QualityRule(self.config.min_rating, self.config.min_reviews))
            
        if self.config.category_whitelist or self.config.category_blacklist:
            self.rules.append(CategoryRule(self.config.category_whitelist, self.config.category_blacklist))
            
        if self.config.keywords:
            self.rules.append(KeywordRule(self.config.keywords))
            
        if self.config.require_socials:
            self.rules.append(SocialMediaRule(self.config.require_socials, self.config.social_logic))

    def should_keep(self, business: Dict[str, Any]) -> bool:
        # Deduplication
        if self.config.deduplicate:
            pid = business.get("place_id")
            if pid:
                if pid in self.seen_ids: return False
                self.seen_ids.add(pid)

        if not self.rules: return True
        
        results = [rule.evaluate(business) for rule in self.rules]
        if self.config.global_logic == "AND":
            return all(results)
        else:
            return any(results)

# ---------------------------------------------------------------------------
# Core Utilities
# ---------------------------------------------------------------------------

def load_data_robust(file_path: Path) -> List[Dict[str, Any]]:
    """Robustly loads leads from either standard JSON or JSONL."""
    # 1. Try loading as a single JSON object/list
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            
            data = json.loads(content)
            
            # If it's a list, return it
            if isinstance(data, list):
                return [i for i in data if isinstance(i, dict)]
            
            # If it's a dict with a "businesses" key (common in some exports)
            if isinstance(data, dict):
                if "businesses" in data and isinstance(data["businesses"], list):
                    return [i for i in data["businesses"] if isinstance(i, dict)]
                # If it's a single lead object
                if "business_name" in data:
                    return [data]
    except (json.JSONDecodeError, MemoryError):
        # Fallback to JSONL
        pass

    # 2. Fallback: Try loading line-by-line (JSONL)
    leads = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        leads.append(obj)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        
    return leads

def discover_categories(file_path: Path) -> List[str]:
    """Scans file to find all unique categories."""
    categories = set()
    data = load_data_robust(file_path)
    for item in data:
        info = item.get("business_info", {})
        if info.get("category"): categories.add(info["category"])
        for c in info.get("all_categories", []):
            if c: categories.add(c)
    return sorted(list(categories))

def process_file(input_path: Path, engine: FilterEngine) -> List[Dict[str, Any]]:
    """Processes a file using the filter engine."""
    data = load_data_robust(input_path)
    kept = [item for item in data if engine.should_keep(item)]
    return kept

def save_outputs(data: List[Dict[str, Any]], input_path: Path):
    """Saves the filtered data in JSONL, CSV, and Excel formats."""
    base_name = input_path.stem
    output_dir = input_path.parent
    
    # JSONL
    jsonl_path = output_dir / f"{base_name}_filtered.jsonl"
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
            
    # Flatten for CSV/Excel
    flat_data = [flatten_business(item) for item in data]
    df = pd.DataFrame(flat_data)
    
    # CSV
    csv_path = output_dir / f"{base_name}_filtered.csv"
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    # Excel
    excel_path = output_dir / f"{base_name}_filtered.xlsx"
    from openpyxl.utils import get_column_letter
    
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Filtered Leads')
        # Basic formatting: Auto-size columns
        worksheet = writer.sheets['Filtered Leads']
        for idx, col in enumerate(df.columns):
            series = df[col]
            # Convert to string and calculate max length safely
            valid_data = series.dropna()
            max_val_len = valid_data.astype(str).map(len).max() if not valid_data.empty else 0
            header_len = len(str(col))
            
            max_len = max(max_val_len, header_len) + 2
            col_letter = get_column_letter(idx + 1)
            worksheet.column_dimensions[col_letter].width = min(max_len, 60) # Cap at 60

    return jsonl_path, csv_path, excel_path

# ---------------------------------------------------------------------------
# Interactive UI
# ---------------------------------------------------------------------------

def run_interactive(input_path: Path) -> FilterConfig:
    config = FilterConfig()
    
    console.print(Panel(f"[bold cyan]Filtration Setup:[/bold cyan] {input_path.name}"))
    
    # Deduplication
    config.deduplicate = Confirm.ask("Enable global deduplication by Place ID?", default=True)
    
    # Logic
    config.global_logic = Prompt.ask("Combine multiple filters using?", choices=["AND", "OR"], default="AND")

    # 1. Contact Info
    if Confirm.ask("Filter by [bold]Contact Info[/bold] (Phone/Website/Email)?", default=False):
        config.require_phone = Confirm.ask("  Require Phone?", default=False)
        config.require_website = Confirm.ask("  Require Website?", default=False)
        config.require_email = Confirm.ask("  Require Email?", default=False)

    # 2. Quality
    if Confirm.ask("Filter by [bold]Business Quality[/bold] (Ratings/Reviews)?", default=False):
        if Confirm.ask("  Filter by average rating?", default=False):
            config.min_rating = FloatPrompt.ask("    Minimum average rating (0-5)", default=4.0)
        if Confirm.ask("  Filter by review count?", default=False):
            config.min_reviews = IntPrompt.ask("    Minimum total reviews", default=10)

    # 3. Social Media
    if Confirm.ask("Filter by [bold]Social Media[/bold] presence?", default=False):
        platforms = ["facebook", "instagram", "twitter", "linkedin", "youtube", "tiktok"]
        selected = []
        for p in platforms:
            if Confirm.ask(f"  Require {p.capitalize()}?", default=False):
                selected.append(p)
        if selected:
            config.require_socials = selected
            config.social_logic = Prompt.ask("  Social media requirement logic?", choices=["AND", "OR"], default="AND")

    # 4. Categories
    if Confirm.ask("Filter by [bold]Categories[/bold]?", default=False):
        mode = Prompt.ask("  Category mode?", choices=["whitelist", "blacklist"], default="whitelist")
        input_mode = Prompt.ask("  Selection mode?", choices=["list", "manual"], default="list")
        
        selected_cats = []
        if input_mode == "list":
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                progress.add_task(description="Scanning unique categories...", total=None)
                all_cats = discover_categories(input_path)
            
            table = Table(title="Available Categories")
            table.add_column("ID", justify="right", style="cyan")
            table.add_column("Name", style="magenta")
            for i, cat in enumerate(all_cats):
                table.add_row(str(i), cat)
            console.print(table)
            
            ids = Prompt.ask("  Enter IDs (comma separated, e.g. 0,2,5)")
            try:
                selected_cats = [all_cats[int(i.strip())] for i in ids.split(",") if i.strip().isdigit()]
            except:
                logger.error("Invalid IDs selected.")
        else:
            manual = Prompt.ask("  Enter categories (comma separated)")
            selected_cats = [c.strip() for c in manual.split(",") if c.strip()]
            
        if mode == "whitelist": config.category_whitelist = selected_cats
        else: config.category_blacklist = selected_cats

    # 5. Keywords
    if Confirm.ask("Filter by [bold]Keywords[/bold] in name/description?", default=False):
        keywords = Prompt.ask("  Enter keywords (comma separated)")
        config.keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    return config

# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Filter scraped Google Maps leads and export to multiple formats.")
    parser.add_argument("file", help="Path to the JSONL file to filter")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    
    # Basic filters via CLI
    parser.add_argument("--phone", action="store_true", help="Require phone number")
    parser.add_argument("--website", action="store_true", help="Require website")
    parser.add_argument("--email", action="store_true", help="Require email")
    parser.add_argument("--min-rating", type=float, help="Minimum average rating")
    parser.add_argument("--min-reviews", type=int, help="Minimum review count")
    parser.add_argument("--whitelist", help="Comma separated categories to keep")
    parser.add_argument("--blacklist", help="Comma separated categories to drop")
    parser.add_argument("--keywords", help="Comma separated keywords to search for")
    parser.add_argument("--socials", help="Comma separated social platforms to require")
    parser.add_argument("--social-logic", choices=["AND", "OR"], default="AND", help="Social media requirement logic")
    parser.add_argument("--logic", choices=["AND", "OR"], default="AND", help="Global filter logic")
    parser.add_argument("--no-dedup", action="store_true", help="Disable deduplication")

    args = parser.parse_args()
    input_path = Path(args.file)
    
    if not input_path.exists():
        logger.error(f"File not found: {input_path}")
        sys.exit(1)

    if args.interactive:
        config = run_interactive(input_path)
    else:
        config = FilterConfig(
            require_phone=args.phone,
            require_website=args.website,
            require_email=args.email,
            min_rating=args.min_rating,
            min_reviews=args.min_reviews,
            category_whitelist=[c.strip() for c in args.whitelist.split(",")] if args.whitelist else [],
            category_blacklist=[c.strip() for c in args.blacklist.split(",")] if args.blacklist else [],
            keywords=[k.strip() for k in args.keywords.split(",")] if args.keywords else [],
            require_socials=[s.strip() for s in args.socials.split(",")] if args.socials else [],
            social_logic=args.social_logic,
            global_logic=args.logic,
            deduplicate=not args.no_dedup
        )

    engine = FilterEngine(config)
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description=f"Filtering {input_path.name}...", total=None)
        filtered_data = process_file(input_path, engine)

    count = len(filtered_data)
    console.print(f"\n[bold green]Success![/bold green] Kept [bold]{count}[/bold] leads.")

    if count > 0:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
            progress.add_task(description="Generating output files...", total=None)
            j, c, e = save_outputs(filtered_data, input_path)
        
        console.print(f"  [cyan]JSONL:[/cyan] {j}")
        console.print(f"  [cyan]CSV:  [/cyan] {c}")
        console.print(f"  [cyan]Excel:[/cyan] {e}")
    else:
        console.print("[yellow]No leads matched your criteria. No files generated.[/yellow]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        logger.exception("An unexpected error occurred")
        sys.exit(1)
