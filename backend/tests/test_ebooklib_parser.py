import argparse
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from html import escape
import logging
from markdownify import markdownify
import os
from pathlib import Path
import posixpath
from urllib.parse import unquote, urldefrag, urlsplit, urlunsplit
import re
import warnings
import markdown2


# Bỏ qua các cảnh báo XML không cần thiết
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

def clean_filename(name):
    """Clean the filename by removing special characters and replacing spaces with underscores."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip().replace(" ", "_")

class EpubToMarkdownConverter:
    """Convert an EPUB into Markdown chapters and extracted images."""

    def __init__(self, epub_path, output_dir=None):
        self.epub_path = Path(epub_path).expanduser()
        self.output_dir = (
            Path(output_dir)
            if output_dir
            else self.epub_path.parent / self.epub_path.stem
        )
        self.images_dir = self.output_dir / "images"

    def convert(self):
        logger.info("Starting EPUB conversion: %s", self.epub_path)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        book = epub.read_epub(str(self.epub_path))
        toc_titles = self._build_toc_index(book.toc)
        self._extract_images(book)
        self._convert_chapters(book, toc_titles)

        logger.info("Conversion complete. Output directory: %s", self.output_dir)

    def _extract_images(self, book):
        logger.info("Extracting images")
        image_types = {ebooklib.ITEM_IMAGE, ebooklib.ITEM_COVER}
        extracted_count = 0
        for item in book.get_items():
            if item.get_type() not in image_types:
                continue
            image_path = self.images_dir / Path(item.get_name()).name
            image_path.write_bytes(item.get_content())
            extracted_count += 1
            if item.get_type() == ebooklib.ITEM_COVER:
                logger.info("Extracted cover image: %s", image_path)
        logger.info("Extracted %d image files", extracted_count)

    def _convert_chapters(self, book, toc_titles):
        logger.info("Converting documents to Markdown")
        document_index = 1

        for item_id, _ in book.spine:
            item = book.get_item_with_id(item_id)
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            soup = BeautifulSoup(item.get_content(), "html.parser")
            self._rewrite_image_sources(soup)
            document_body = soup.body or soup
            markdown_content = markdownify(
                str(document_body), heading_style="ATX"
            ).strip()

            if markdown_content:
                document_title = toc_titles.get(self._href_key(item.get_name()))
                chapter_path = self.output_dir / self._document_filename(
                    document_index, document_title, soup, item.get_name()
                )
                chapter_path.write_text(markdown_content, encoding="utf-8")
                document_index += 1

    @staticmethod
    def _rewrite_image_sources(soup):
        for image in soup.find_all("img"):
            if image.get("src"):
                image["src"] = f"images/{Path(urldefrag(image['src'])[0]).name}"

    @staticmethod
    def _build_toc_index(toc):
        toc_titles = {}
        for entry in toc:
            if getattr(entry, "href", None) and getattr(entry, "title", None):
                toc_titles[EpubToMarkdownConverter._href_key(entry.href)] = (
                    entry.title.strip()
                )
            toc_titles.update(
                EpubToMarkdownConverter._build_toc_index(
                    getattr(entry, "children", ())
                )
            )
        return toc_titles

    @staticmethod
    def _href_key(href):
        path, _ = urldefrag(unquote(href))
        return posixpath.normpath(path).lstrip("./")

    @classmethod
    def _document_filename(cls, document_index, toc_title, soup, item_name):
        document_title = toc_title or cls._heading_title(soup)
        if not document_title:
            document_title = Path(item_name).stem.replace("_", " ")
        document_title = clean_filename(document_title) or "Document"
        return f"{document_index:02d}_{document_title}.md"

    @staticmethod
    def _heading_title(soup):
        headings = [
            heading.get_text(" ", strip=True)
            for heading in soup.find_all(["h1", "h2", "h3"])
            if heading.get_text(" ", strip=True)
        ]
        if not headings:
            return ""

        first_heading = headings[0]
        if re.fullmatch(r"\d+\.", first_heading) and len(headings) > 1:
            return f"{first_heading} {headings[1]}"
        return first_heading


def epub_to_markdown_structure(epub_path, output_dir=None):
    """Backward-compatible wrapper for the converter class."""
    EpubToMarkdownConverter(epub_path, output_dir).convert()


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Convert an EPUB file into Markdown chapters and images."
    )
    parser.add_argument("epub_path", type=Path, help="Path to the source EPUB file")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Directory for generated Markdown files and images (default: beside the EPUB)",
    )
    return parser.parse_args(args)

def main(args=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    arguments = parse_args(args)
    try:
        converter = EpubToMarkdownConverter(arguments.epub_path, arguments.output_dir)
        converter.convert()
        logger.info("EPUB conversion succeeded")
        markdown_dir = converter.output_dir
        html_output_path = converter.epub_path.with_suffix(".html")
        convert_markdown_to_one_html_ebook(markdown_dir, html_output_path)
        logger.info("HTML conversion succeeded")
        logger.info("HTML ebook created at: %s", html_output_path)
    except Exception:
        logger.exception("EPUB conversion failed")
        return 1
    return 0

class MarkdownEbookRenderer:
        """Render Markdown chapters as a navigable, single-file HTML ebook."""

        MARKDOWN_EXTRAS = ["fenced-code-blocks", "footnotes", "strike", "tables"]

        def __init__(self, markdown_dir, output_html_path):
                self.markdown_dir = Path(markdown_dir)
                self.output_html_path = Path(output_html_path)

        def render(self):
                if not self.markdown_dir.is_dir():
                        raise ValueError(f"{self.markdown_dir} is not a valid directory")

                markdown_files = sorted(
                        self.markdown_dir.glob("*.md"), key=self._natural_sort_key
                )
                if not markdown_files:
                        raise ValueError(f"No Markdown files found in {self.markdown_dir}")

                chapters = [
                        self._render_chapter(index, markdown_file)
                        for index, markdown_file in enumerate(markdown_files, start=1)
                ]
                self.output_html_path.parent.mkdir(parents=True, exist_ok=True)
                self.output_html_path.write_text(
                        self._render_page(chapters), encoding="utf-8"
                )
                logger.info("Rendered %d Markdown files", len(markdown_files))

        @staticmethod
        def _natural_sort_key(path):
                return [
                        int(part) if part.isdigit() else part.lower()
                        for part in re.split(r"(\d+)", path.name)
                ]

        def _render_chapter(self, index, markdown_file):
                markdown_content = markdown_file.read_text(encoding="utf-8")
                chapter_html = markdown2.markdown(
                        markdown_content, extras=self.MARKDOWN_EXTRAS
                )
                chapter_html = self._rewrite_asset_urls(chapter_html, markdown_file)
                return {
                        "id": f"chapter-{index}",
                        "title": self._chapter_title(markdown_file),
                        "html": chapter_html,
                }

        def _rewrite_asset_urls(self, chapter_html, markdown_file):
                soup = BeautifulSoup(chapter_html, "html.parser")
                for image in soup.find_all("img", src=True):
                        image["src"] = self._relative_asset_url(image["src"], markdown_file)
                self._add_reading_classes(soup)
                return str(soup)

        @staticmethod
        def _add_reading_classes(soup):
            heading_classes = {
                "h1": "mb-6 text-4xl font-semibold leading-tight tracking-tight text-stone-900 sm:text-5xl",
                "h2": "mb-5 mt-10 text-3xl font-semibold leading-tight tracking-tight text-stone-900 sm:text-4xl",
                "h3": "mb-4 mt-8 text-2xl font-semibold leading-tight text-stone-900",
            }
            for tag_name, classes in heading_classes.items():
                for heading in soup.find_all(tag_name):
                    heading["class"] = classes.split()
            for paragraph in soup.find_all("p"):
                paragraph["class"] = ["my-5", "text-lg", "leading-8", "text-stone-700"]
            for list_tag in soup.find_all(["ul", "ol"]):
                list_tag["class"] = ["my-5", "space-y-2", "pl-6", "text-lg", "text-stone-700"]
            for link in soup.find_all("a"):
                link["class"] = ["text-[#9b4d32]", "underline", "decoration-[#d9a48e]", "underline-offset-2", "hover:text-[#703522]"]
            for blockquote in soup.find_all("blockquote"):
                blockquote["class"] = ["my-8", "border-l-4", "border-[#a34f32]", "pl-5", "italic", "text-stone-500"]
            for image in soup.find_all("img"):
                image["class"] = ["mx-auto", "my-8", "h-auto", "max-w-full", "rounded-sm", "shadow-sm"]
            for table in soup.find_all("table"):
                table["class"] = ["my-8", "w-full", "border-collapse", "text-left", "text-base"]
            for cell in soup.find_all(["th", "td"]):
                cell["class"] = ["border", "border-stone-200", "px-3", "py-2"]
            for pre in soup.find_all("pre"):
                pre["class"] = ["my-6", "overflow-x-auto", "rounded-lg", "bg-[#1f2937]", "p-5", "text-sm", "leading-6", "text-[#f8fafc]", "shadow-inner"]
            for code in soup.find_all("code"):
                if code.parent.name == "pre":
                    code["class"] = ["bg-transparent", "p-0", "font-mono", "text-[#f8fafc]"]
                else:
                    code["class"] = ["rounded", "bg-[#f3eee8]", "px-1.5", "py-0.5", "font-mono", "text-[0.9em]", "font-semibold", "text-[#8f3d1f]"]

        def _relative_asset_url(self, source_url, markdown_file):
                parsed_url = urlsplit(source_url)
                if parsed_url.scheme or parsed_url.netloc or parsed_url.path.startswith("/"):
                        return source_url

                source_path = markdown_file.parent / unquote(parsed_url.path)
                relative_path = os.path.relpath(
                        source_path.resolve(), self.output_html_path.parent.resolve()
                ).replace(os.sep, "/")
                return urlunsplit(
                        ("", "", relative_path, parsed_url.query, parsed_url.fragment)
                )

        @staticmethod
        def _chapter_title(markdown_file):
                title = re.sub(r"^\d+_", "", markdown_file.stem)
                return title.replace("_", " ") or markdown_file.stem

        def _render_page(self, chapters):
                navigation = "\n".join(
                        f'<li><a class="block rounded px-3 py-2 text-sm text-stone-600 transition hover:bg-[#f1e0d7] hover:text-[#703522] focus:outline-none focus:ring-2 focus:ring-[#a34f32]" href="#{chapter["id"]}">{escape(chapter["title"])}</a></li>'
                        for chapter in chapters
                )
                content = "\n".join(
                        f'<article class="chapter min-h-[50vh] border-b border-stone-200 py-10 first:pt-4 last:border-b-0" id="{chapter["id"]}">'
                        f'<div class="chapter-content">{chapter["html"]}</div></article>'
                        for chapter in chapters
                )
                title = self.output_html_path.stem.replace("_", " ")
                return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>{self._styles()}</style>
</head>
<body class="bg-[#fbfaf7] text-stone-800 antialiased">
    <a class="fixed left-4 top-[-4rem] z-50 rounded bg-[#a34f32] px-4 py-2 text-white transition focus:top-4" href="#book-content">Skip to book content</a>
    <header class="sticky top-0 z-20 border-b border-stone-200/80 bg-[#fbfaf7]/95 shadow-sm backdrop-blur">
        <div class="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <button class="menu-toggle inline-flex shrink-0 items-center gap-2 rounded border border-stone-300 bg-[#f1eee7] px-3 py-2 text-sm font-semibold text-stone-800 transition hover:bg-[#ead8ce] focus:outline-none focus:ring-2 focus:ring-[#a34f32] lg:hidden" type="button" aria-controls="book-nav" aria-expanded="false">
                <span aria-hidden="true">&#9776;</span><span>Contents</span>
            </button>
            <label class="sr-only" for="book-search">Search this book</label>
            <div class="relative min-w-0 flex-1">
                <span class="pointer-events-none absolute inset-y-0 left-3 flex items-center text-stone-400" aria-hidden="true">&#128269;</span>
                <input class="w-full rounded border border-stone-300 bg-white py-2 pl-9 pr-20 text-sm text-stone-800 outline-none transition placeholder:text-stone-400 focus:border-[#a34f32] focus:ring-2 focus:ring-[#a34f32]/20" id="book-search" type="search" placeholder="Search this book..." autocomplete="off">
                <button class="absolute inset-y-1 right-1 hidden rounded px-2 text-xs font-semibold text-stone-500 hover:bg-stone-100 hover:text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#a34f32]" id="clear-search" type="button">Clear</button>
            </div>
            <span class="hidden whitespace-nowrap text-xs text-stone-500 sm:inline" id="search-status" aria-live="polite">Search {len(chapters)} sections</span>
            <button class="hidden rounded p-2 text-stone-500 hover:bg-stone-100 hover:text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#a34f32] sm:inline-flex" id="previous-match" type="button" title="Previous matching section" aria-label="Previous matching section">&#8593;</button>
            <button class="hidden rounded p-2 text-stone-500 hover:bg-stone-100 hover:text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#a34f32] sm:inline-flex" id="next-match" type="button" title="Next matching section" aria-label="Next matching section">&#8595;</button>
        </div>
    </header>
    <div class="relative lg:flex">
    <div class="nav-backdrop fixed inset-0 z-20 hidden bg-stone-900/30 lg:hidden" aria-hidden="true"></div>
    <aside class="book-nav fixed inset-y-0 left-0 z-30 w-72 -translate-x-full overflow-y-auto border-r border-stone-200 bg-[#f1eee7] px-5 pb-8 pt-24 shadow-xl transition-transform duration-200 lg:sticky lg:top-16 lg:h-[calc(100vh-4rem)] lg:w-72 lg:shrink-0 lg:translate-x-0 lg:shadow-none" id="book-nav" aria-label="Book contents">
        <div class="border-b border-stone-300 pb-6">
            <p class="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-[#a34f32]">Reading edition</p>
            <h1 class="text-xl font-semibold leading-tight text-stone-900">{escape(title)}</h1>
        </div>
        <nav class="mt-6" aria-label="Chapters">
            <ol class="grid gap-1">
                {navigation}
            </ol>
        </nav>
    </aside>
    <main class="mx-auto max-w-3xl px-5 pb-24 pt-8 sm:px-8 lg:mx-auto lg:max-w-3xl lg:flex-1 lg:px-8" id="book-content">
        {content}
    </main>
    </div>
    <div class="fixed bottom-4 right-4 z-10 rounded bg-stone-900 px-3 py-2 text-xs text-white shadow-lg" id="search-hint">Press <kbd class="rounded bg-white/20 px-1">/</kbd> to search</div>
    <script src="https://code.jquery.com/jquery-3.7.1.min.js" crossorigin="anonymous"></script>
    <script>
{self._script()}
    </script>
</body>
</html>
"""

        @staticmethod
        def _styles():
                return """
.search-match { background: #fde68a; border-radius: .15rem; color: inherit; padding: 0 .1rem; }
.search-current { outline: 3px solid #c2410c; outline-offset: 3px; }
    @media print {
    header, .book-nav, .nav-backdrop, #search-hint { display: none !important; }
    main { margin: 0 !important; max-width: none !important; }
}
.chapter-content code:not(pre code) {
    color: #8f3d1f;
    background: #f3eee8;
}
.chapter-content pre {
    color: #f8fafc;
    background: #1f2937;
}
.chapter-content pre code {
    color: #f8fafc;
    background: transparent;
}
"""

        @staticmethod
        def _script():
                return """
$(function () {
    const $menuButton = $('.menu-toggle');
    const $navigation = $('.book-nav');
    const $backdrop = $('.nav-backdrop');
    const $links = $('.book-nav a');
    const $chapters = $('.chapter');
    const $search = $('#book-search');
    const $clearSearch = $('#clear-search');
    const $status = $('#search-status');
    const $previous = $('#previous-match');
    const $next = $('#next-match');
    const $searchHint = $('#search-hint');
    let matchingChapters = [];
    let currentMatch = -1;

    function setNavigationOpen(isOpen) {
        $navigation.toggleClass('translate-x-0', isOpen);
        $navigation.toggleClass('-translate-x-full', !isOpen);
        $backdrop.toggleClass('hidden', !isOpen);
        $menuButton.attr('aria-expanded', String(isOpen));
    }

    $menuButton.on('click', function () {
        setNavigationOpen(!$navigation.hasClass('translate-x-0'));
    });
    $backdrop.on('click', function () { setNavigationOpen(false); });
    $links.on('click', function () { setNavigationOpen(false); });

    function escapeRegExp(value) {
        return value.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
    }

    function restoreChapter($chapter) {
        const originalHtml = $chapter.data('original-html');
        $chapter.find('.chapter-content').html(originalHtml);
    }

    function highlightTerms(element, terms) {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        const textNodes = [];
        let node;
        while ((node = walker.nextNode())) {
            if (node.parentElement.closest('script, style, mark')) continue;
            textNodes.push(node);
        }

        const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
        textNodes.forEach((textNode) => {
            if (!pattern.test(textNode.nodeValue)) {
                pattern.lastIndex = 0;
                return;
            }
            pattern.lastIndex = 0;
            const fragment = document.createDocumentFragment();
            textNode.nodeValue.split(pattern).forEach((part) => {
                if (terms.some((term) => part.toLowerCase() === term.toLowerCase())) {
                    const mark = document.createElement('mark');
                    mark.className = 'search-match';
                    mark.textContent = part;
                    fragment.appendChild(mark);
                } else {
                    fragment.appendChild(document.createTextNode(part));
                }
            });
            textNode.parentNode.replaceChild(fragment, textNode);
        });
    }

    function updateSearchStatus(query) {
        if (!query) {
            $status.text(`Search ${$chapters.length} sections`);
            return;
        }
        if (!matchingChapters.length) {
            $status.text('No matching sections');
            return;
        }
        $status.text(`${matchingChapters.length} matching ${matchingChapters.length === 1 ? 'section' : 'sections'}`);
    }

    function runSearch() {
        const query = $.trim($search.val());
        const terms = query.toLowerCase().split(/\\s+/).filter(Boolean);
        matchingChapters = [];
        currentMatch = -1;

        $chapters.each(function () {
            const $chapter = $(this);
            if (!$chapter.data('original-html')) {
                $chapter.data('original-html', $chapter.find('.chapter-content').html());
            }
            restoreChapter($chapter);
            const chapterText = $chapter.text().toLowerCase();
            const matches = !terms.length || terms.every((term) => chapterText.includes(term));
            $chapter.toggle(matches);
            const chapterId = $chapter.attr('id');
            $links.filter(function () {
                return $(this).attr('href') === `#${chapterId}`;
            }).toggle(matches);
            if (matches && terms.length) {
                matchingChapters.push(this);
                highlightTerms($chapter.find('.chapter-content')[0], terms);
            }
        });

        $clearSearch.toggleClass('hidden', !query);
        $previous.toggleClass('hidden', !matchingChapters.length);
        $next.toggleClass('hidden', !matchingChapters.length);
        $searchHint.toggleClass('hidden', Boolean(query));
        updateSearchStatus(query);
    }

    function goToMatch(direction) {
        if (!matchingChapters.length) return;
        currentMatch = (currentMatch + direction + matchingChapters.length) % matchingChapters.length;
        $('.search-current').removeClass('search-current');
        const $chapter = $(matchingChapters[currentMatch]);
        $chapter.addClass('search-current');
        $chapter[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    $search.on('input', runSearch);
    $search.on('keydown', function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            goToMatch(event.shiftKey ? -1 : 1);
        }
    });
    $clearSearch.on('click', function () {
        $search.val('').trigger('input').trigger('focus');
    });
    $previous.on('click', function () { goToMatch(-1); });
    $next.on('click', function () { goToMatch(1); });
    $(document).on('keydown', function (event) {
        if (event.key === '/' && document.activeElement !== $search[0]) {
            event.preventDefault();
            $search.trigger('focus');
        }
        if (event.key === 'Escape' && $search.val()) {
            $clearSearch.trigger('click');
        }
    });

    $chapters.each(function () {
        $(this).data('original-html', $(this).find('.chapter-content').html());
    });
    $links.first().addClass('bg-[#f1e0d7] text-[#703522]');
});
"""


def convert_markdown_to_one_html_ebook(folder_md, output_html_file):
        """Convert Markdown chapters to one navigable HTML ebook."""
        MarkdownEbookRenderer(folder_md, output_html_file).render()


if __name__ == "__main__":
    raise SystemExit(main())