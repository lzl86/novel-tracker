"""
Universal Heuristic Content Extractor.
Extracts main novel chapter text from heterogeneous HTML pages without hardcoded XPath/CSS selectors.
Uses trafilatura as primary engine with DOM text-density fallback.
"""

from typing import Optional
from bs4 import BeautifulSoup
import trafilatura


class HeuristicExtractor:
    def __init__(self):
        pass

    def extract_article_text(self, html_content: str, url: Optional[str] = None) -> str:
        """
        Heuristically extract the main story text from an arbitrary HTML document.
        """
        if not html_content or not html_content.strip():
            return ""

        # Engine 1: Trafilatura (State of the art web text extraction)
        try:
            extracted_text = trafilatura.extract(
                html_content,
                url=url,
                include_comments=False,
                include_tables=False,
                include_images=False,
                include_links=False,
                output_format='txt',
                favor_recall=True
            )
            if extracted_text and len(extracted_text.strip()) > 200:
                return extracted_text.strip()
        except Exception:
            pass

        # Engine 2: DOM Text-Density / Paragraph Cluster Fallback
        return self._dom_density_fallback(html_content)

    def _dom_density_fallback(self, html_content: str) -> str:
        """
        Fallback parser: Cleans non-content elements and selects the highest text-density node.
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove noise tags
            for tag in soup([
                "script", "style", "iframe", "header", "footer", "nav",
                "aside", "noscript", "svg", "button", "input", "form"
            ]):
                tag.decompose()

            # Remove known comment / ad class containers
            for noisy in soup.select(".comment, .comments, .sidebar, .ad, .advertisement, .nav, .header, .footer"):
                noisy.decompose()

            # Search candidates: divs / articles with high paragraph counts
            candidate_blocks = []
            for container in soup.find_all(["div", "article", "section", "main"]):
                p_tags = container.find_all("p", recursive=False)
                if len(p_tags) >= 3:
                    text_len = sum(len(p.get_text(strip=True)) for p in p_tags)
                    candidate_blocks.append((text_len, "\n\n".join(p.get_text(strip=True) for p in p_tags if p.get_text(strip=True))))
                else:
                    # Check direct text length
                    direct_text = container.get_text("\n", strip=True)
                    if len(direct_text) > 300:
                        candidate_blocks.append((len(direct_text), direct_text))

            if candidate_blocks:
                candidate_blocks.sort(key=lambda x: x[0], reverse=True)
                return candidate_blocks[0][1]

            # Last resort: all p tags on page
            all_p = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 10]
            if all_p:
                return "\n\n".join(all_p)

            return soup.get_text("\n", strip=True)
        except Exception:
            return ""
