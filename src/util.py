"""Generic utilities for the pug bot."""

import os


def random_human_readable_phrase():
    """Generates a random human readable phrase to work as an identifier.
       Can be used for the !scrambles, to make it easier for players to refer
       to specific scramble permutations via voice chat by using these phrases.
    """
    base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "..", "static", "phrase_gen")
    with open(file=os.path.join(base_path, "nouns.txt"), mode="r",
              encoding="utf-8") as f_nouns:
        nouns = f_nouns.readlines()
    with open(file=os.path.join(base_path, "adjectives.txt"), mode="r",
              encoding="utf-8") as f_adjs:
        adjectives = f_adjs.readlines()
    phrase = (f"{adjectives[random.randint(0, len(adjectives) - 1)]} "
              f"{nouns[random.randint(0, len(nouns) - 1)]}")
    return phrase.replace("\n", "").lower()
