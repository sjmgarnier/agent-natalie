from natalie.features.links import (
    find_wikilinks,
    link_matches_note,
    normalize_wikilinks,
    resolve_link_target,
    rewrite_links_in_content,
    stem_for_path,
)
from natalie.features.memory import index_note
from tests.helpers import write_note


def test_find_wikilinks_splits_path_heading_alias():
    content = "See [[Projects/Alpha/Meeting Notes#Action Items|see here]] for details."
    matches = find_wikilinks(content)
    assert len(matches) == 1
    m = matches[0]
    assert m.path_part == "Projects/Alpha/Meeting Notes"
    assert m.heading == "Action Items"
    assert m.block is None
    assert m.alias == "see here"
    assert not m.is_embed


def test_find_wikilinks_detects_embed_and_block_ref():
    content = "![[Diagram.png]] and [[Note^abc123]]"
    matches = find_wikilinks(content)
    assert matches[0].is_embed
    assert matches[0].path_part == "Diagram.png"
    assert matches[1].block == "abc123"
    assert matches[1].heading is None


def test_find_wikilinks_bare_link_has_no_suffixes():
    matches = find_wikilinks("[[Meeting Notes]]")
    assert len(matches) == 1
    assert matches[0].path_part == "Meeting Notes"
    assert matches[0].heading is None
    assert matches[0].alias is None


def test_find_wikilinks_skips_fenced_code_block():
    content = "before\n```\n[[Projects/Alpha/Example]]\n```\nafter [[Real Link]]"
    matches = find_wikilinks(content)
    assert len(matches) == 1
    assert matches[0].path_part == "Real Link"


def test_find_wikilinks_skips_inline_code_span():
    content = "use `[[Projects/Alpha/Example]]` syntax, or [[Real Link]]"
    matches = find_wikilinks(content)
    assert len(matches) == 1
    assert matches[0].path_part == "Real Link"


def test_canonical_preserves_heading_and_alias():
    matches = find_wikilinks("[[Projects/Alpha/Meeting Notes#Action Items|see here]]")
    rendered = matches[0].canonical("Meeting Notes")
    assert rendered == "[[Meeting Notes#Action Items|see here]]"


def test_canonical_preserves_embed_bang():
    matches = find_wikilinks("![[Projects/Diagram.png]]")
    rendered = matches[0].canonical("Diagram.png")
    assert rendered == "![[Diagram.png]]"


def test_stem_for_path():
    assert stem_for_path("Projects/Alpha/Meeting Notes.md") == "Meeting Notes"


def test_resolve_link_target_unique_returns_bare_stem(db, vault):
    index_note(db, vault, write_note(vault, "Projects/Alpha/Meeting Notes.md", "body"))
    assert resolve_link_target(db, "Projects/Alpha/Meeting Notes.md") == "Meeting Notes"


def test_resolve_link_target_collision_returns_disambiguating_path(db, vault):
    index_note(db, vault, write_note(vault, "Projects/Alpha/Meeting Notes.md", "a"))
    index_note(db, vault, write_note(vault, "Projects/Beta/Meeting Notes.md", "b"))
    assert resolve_link_target(db, "Projects/Alpha/Meeting Notes.md") == "Alpha/Meeting Notes"
    assert resolve_link_target(db, "Projects/Beta/Meeting Notes.md") == "Beta/Meeting Notes"


def test_normalize_wikilinks_strips_path_qualified_link(db, vault):
    index_note(db, vault, write_note(vault, "Projects/Alpha/Meeting Notes.md", "body"))
    content = "See [[Projects/Alpha/Meeting Notes]] for details."
    assert normalize_wikilinks(db, content) == "See [[Meeting Notes]] for details."


def test_normalize_wikilinks_leaves_bare_link_unchanged(db, vault):
    content = "See [[Meeting Notes]] for details."
    assert normalize_wikilinks(db, content) == content


def test_normalize_wikilinks_preserves_alias_and_heading(db, vault):
    index_note(db, vault, write_note(vault, "Projects/Alpha/Meeting Notes.md", "body"))
    content = "[[Projects/Alpha/Meeting Notes#Action Items|see here]]"
    assert normalize_wikilinks(db, content) == "[[Meeting Notes#Action Items|see here]]"


def test_normalize_wikilinks_retains_disambiguating_path_on_collision(db, vault):
    index_note(db, vault, write_note(vault, "Projects/Alpha/Meeting Notes.md", "a"))
    index_note(db, vault, write_note(vault, "Projects/Beta/Meeting Notes.md", "b"))
    content = "[[Projects/Alpha/Meeting Notes]]"
    assert normalize_wikilinks(db, content) == "[[Alpha/Meeting Notes]]"


def test_normalize_wikilinks_leaves_code_block_untouched(db, vault):
    content = "```\n[[Projects/Alpha/Example]]\n```"
    assert normalize_wikilinks(db, content) == content


def test_link_matches_note_bare_and_path_qualified():
    assert link_matches_note("Meeting Notes", "Projects/Alpha/Meeting Notes.md")
    assert link_matches_note("Alpha/Meeting Notes", "Projects/Alpha/Meeting Notes.md")
    assert not link_matches_note("Beta/Meeting Notes", "Projects/Alpha/Meeting Notes.md")
    assert not link_matches_note("Other Note", "Projects/Alpha/Meeting Notes.md")


def test_rewrite_links_in_content_renames_bare_link(db, vault):
    index_note(db, vault, write_note(vault, "New Name.md", "body"))
    content = "See [[Old Name]] for details."
    new_content, changed = rewrite_links_in_content(db, content, "Old Name.md", "New Name.md")
    assert changed
    assert new_content == "See [[New Name]] for details."


def test_rewrite_links_in_content_repairs_legacy_path_qualified_link(db, vault):
    index_note(db, vault, write_note(vault, "Projects/Alpha/Note.md", "body"))
    content = "[[old/folder/Note]]"
    new_content, changed = rewrite_links_in_content(
        db, content, "old/folder/Note.md", "Projects/Alpha/Note.md"
    )
    assert changed
    assert new_content == "[[Note]]"


def test_rewrite_links_in_content_leaves_unrelated_links_untouched(db, vault):
    content = "[[Unrelated Note]]"
    new_content, changed = rewrite_links_in_content(db, content, "Old Name.md", "New Name.md")
    assert not changed
    assert new_content == content


def test_rewrite_links_in_content_folder_only_move_is_not_changed(db, vault):
    """A folder-only move (basename unchanged, no collision) re-resolves a bare
    link to the same text — changed must reflect that, not just "a match was found",
    or note_move would needlessly invalidate every backlinking note's embedding."""
    index_note(db, vault, write_note(vault, "Projects/Beta/Note.md", "body"))
    content = "See [[Note]] for details."
    new_content, changed = rewrite_links_in_content(
        db, content, "Projects/Alpha/Note.md", "Projects/Beta/Note.md"
    )
    assert not changed
    assert new_content == content


def test_rewrite_links_in_content_skips_ambiguous_bare_link_on_collision(db, vault):
    """A bare [[Note]] link is ambiguous when another note shares that basename —
    rewriting it would silently redirect a link that may have meant the other note.
    The unambiguous path-qualified reference to the moved note is still repaired."""
    index_note(db, vault, write_note(vault, "Projects/Beta/Note.md", "other note, untouched by the move"))
    index_note(db, vault, write_note(vault, "Archive/Note.md", "the moved note, now living here"))
    content = "[[Note]] and [[Projects/Alpha/Note]]"
    new_content, changed = rewrite_links_in_content(db, content, "Projects/Alpha/Note.md", "Archive/Note.md")
    assert changed
    assert new_content == "[[Note]] and [[Archive/Note]]"
