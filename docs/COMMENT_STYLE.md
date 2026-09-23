# Comment style

The rule this codebase follows: **a comment explains why, the code already says what.**
If a comment restates the line below it, delete the comment.

## Module docstrings

Every file under `splitmate/` opens with one. It says what the module is for and,
where it matters, what constraint shaped it. The application factory's says why
its helpers import inside the function body (a circular import); `money.py`'s says
why every function redistributes leftover minor units.

## Docstrings on everything exported

Every public class, function, method and property has one. Private helpers
(`_leading_underscore`) have one when the reason for their existence is not
obvious from the name.

One line where one line is enough:

```python
def has_member(self, user_id: int) -> bool:
    """Whether ``user_id`` belongs to this group. The access checks start here."""
```

More when there is something a reader would otherwise have to work out:

```python
def get_group_or_404(group_id: int) -> Group:
    """Fetch a group the signed-in user belongs to, or abort.

    A non-member gets a 404 rather than a 403 so the app does not confirm that
    a group id exists to someone who has no business knowing.
    """
```

The second paragraph is the point. A reader can see it returns 404; they cannot
see that the status code was chosen rather than defaulted.

## Comments inside a function

Reserved for a decision, a constraint, or a trap. Some examples from this repo:

```python
# Screen before quantizing: an infinity or a 999-digit exponent makes
# quantize raise, and any comparison against a NaN raises too, so an
# unscreened amount leaves here as a 500 rather than a message.
```

```python
# Existing rows are updated in place rather than deleted and recreated. A
# delete-then-insert would put both versions of the same (expense, user) pair
# in one flush, and the unique constraint rejects that.
```

Both record something that was learned. Neither describes what the next line does.

## What is not written

- No narration: `# loop over the members` above a loop over the members.
- No commented-out code. Git has it.
- No `# TODO` without a name and a reason; an untracked TODO is a wish.
- No banner comments made of punctuation, except the short `# -- section ---`
  dividers already used inside the larger model classes.

## Plain ASCII

No em dashes, en dashes, arrows or dingbats anywhere: prose, comments, commit
messages or interface strings. Use `-`, `->` or rewrite the sentence. CI enforces
this, and the one exemption would be a test whose subject is the characters
themselves.

Note that this is about the characters in the file, not the glyphs on screen: a
coding font with ligatures can draw `->` as a single arrow, which no text check
can see.

## Tests

Test names are sentences: `test_a_negative_amount_stays_a_number`. Where a test
exists because something once went wrong, its docstring says what went wrong, so
nobody deletes it as redundant:

```python
def test_something_that_parses_as_a_number_is_left_alone(number):
    """Escaping every leading sign would turn every refund into text.
    ...
    """
```
