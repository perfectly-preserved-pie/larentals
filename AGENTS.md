# Documentation for Python and JavaScript changes

When you add or change a function, read its body and callers before writing its
docstring or JSDoc. Explain the behavior a maintainer could miss from the name
and signature: why the function exists, important input or output boundaries,
fallbacks, side effects, or a dependency on another component. Give the reader
a useful reason for a rule or threshold when the code does not make it obvious.

Use plain, specific language. A short summary plus one focused paragraph is
usually enough. Skip filler, repeated type information, and narration of each
statement. For tiny helpers, keep the explanation short and concrete; do not invent a
rationale just to fill space. Keep Python Args and Returns/Yields sections, and JS
@param/@returns tags, accurate where they are already used. Do not write
"the value" or "the result" when a concrete description is available.

When editing a function with a thin existing comment, improve the comment as
part of the change. For example:

    """Accept a geocoder result only when it still matches the listing address.

    A nearby point can look plausible while belonging to another street, so
    compare the returned route, number, and ZIP before moving the map pin.

    Args:
        address: Listing address sent to the geocoder.
        result: Candidate returned by the geocoder.

    Returns:
        Whether the candidate still describes that listing address.
    """

For JS, use the same approach in JSDoc: say why an event is emitted or why a
fallback is chosen, then keep type tags concise. Do not add a second sentence
that merely restates the first.

The documentation check in tests/test_docstring_depth.py blocks literal
one-line production docstrings and increases in the existing summary-only
Python and JavaScript backlogs. When you improve older comments, lower the
relevant baseline count.
