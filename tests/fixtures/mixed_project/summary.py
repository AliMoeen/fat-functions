"""Order summaries: comments, blank lines and docstrings are not code."""


def describe(order):
    """Return a one-line summary of an order.

    Blank lines and comments in here are not code either.
    """
    # Start with the id.
    parts = [order.id]

    # Add the total when there is one.
    if order.total:
        parts.append(str(order.total))  # a trailing comment keeps the line
    return " ".join(parts)
