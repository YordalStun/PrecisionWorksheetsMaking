"""The three word-list tiers a child progresses through, in order.

Each tier's word order is the canonical published order from the source
material (a Twinkl resource in each case) - First 100 is frequency-rank
order, Next 200 and Year 3/4 are alphabetical. A child is assumed to have
fully mastered every tier before the one they're currently on - see
tracking.py for how that's used when picking words to practise.
"""

from __future__ import annotations

from dataclasses import dataclass

FIRST_100 = (
    "the", "and", "a", "to", "said", "in", "he", "I", "of", "it",
    "was", "you", "they", "on", "she", "is", "for", "at", "his", "but",
    "that", "with", "all", "we", "can", "are", "up", "had", "my", "her",
    "what", "there", "out", "this", "have", "went", "be", "like", "some", "so",
    "not", "then", "were", "go", "little", "as", "make", "asked", "no", "mum",
    "one", "them", "do", "me", "down", "dad", "big", "when", "it's", "see",
    "looked", "very", "look", "don't", "come", "saw", "an", "will", "into", "back",
    "from", "children", "him", "Mr", "get", "just", "now", "came", "oh", "about",
    "got", "their", "people", "your", "put", "could", "house", "old", "too", "by",
    "day", "made", "time", "I'm", "if", "help", "Mrs", "called", "here", "off",
)

NEXT_200 = (
    "across", "after", "again", "air", "along", "am", "animals", "another",
    "any", "around", "away", "baby", "bad", "bear", "because", "bed",
    "been", "before", "began", "best", "better", "birds", "boat", "book",
    "box", "boy", "can't", "car", "cat", "clothes", "cold", "coming",
    "couldn't", "cried", "dark", "did", "didn't", "different", "dog", "door",
    "dragon", "duck", "each", "eat", "eggs", "end", "even", "ever",
    "every", "everyone", "eyes", "fast", "feet", "fell", "find", "first",
    "fish", "floppy", "fly", "food", "found", "fox", "friends", "fun",
    "garden", "gave", "giant", "girl", "going", "gone", "good", "gran",
    "grandad", "great", "green", "grow", "hard", "has", "hat", "he's",
    "head", "home", "horse", "hot", "how", "I'll", "I've", "inside",
    "its", "jumped", "keep", "key", "king", "know", "last", "laughed",
    "let", "let's", "liked", "live", "lived", "long", "looking", "looks",
    "lots", "magic", "man", "many", "may", "miss", "more", "morning",
    "most", "mother", "mouse", "much", "must", "narrator", "need", "never",
    "new", "next", "night", "one", "only", "or", "other", "our",
    "over", "park", "place", "plants", "play", "please", "pulled", "queen",
    "rabbit", "ran", "really", "red", "right", "river", "room", "round",
    "run", "sat", "say", "school", "sea", "shouted", "sleep", "small",
    "snow", "something", "soon", "still", "stop", "stopped", "suddenly", "sun",
    "take", "tea", "tell", "than", "that's", "there's", "these", "thing",
    "things", "think", "thought", "three", "through", "told", "took", "top",
    "town", "tree", "trees", "two", "under", "us", "use", "want",
    "wanted", "water", "way", "well", "we're", "where", "which", "white",
    "who", "why", "wind", "window", "wish", "work", "would", "yes",
)

YEAR_3_4 = (
    "accident", "accidentally", "actual", "actually", "address", "answer",
    "appear", "arrive", "believe", "bicycle", "breath", "breathe", "build",
    "busy", "business", "calendar", "caught", "centre", "century", "certain",
    "circle", "complete", "consider", "continue", "decide", "describe",
    "different", "difficult", "disappear", "early", "earth", "eight",
    "eighth", "enough", "exercise", "experience", "experiment", "extreme",
    "famous", "favourite", "February", "forward", "forwards", "fruit",
    "grammar", "group", "guard", "guide", "heard", "heart", "height",
    "history", "imagine", "increase", "important", "interest", "island",
    "knowledge", "learn", "length", "library", "material", "medicine",
    "mention", "minute", "natural", "naughty", "notice", "occasion",
    "occasionally", "often", "opposite", "ordinary", "particular", "peculiar",
    "perhaps", "popular", "position", "possess", "possession", "possible",
    "potatoes", "pressure", "probably", "promise", "purpose", "quarter",
    "question", "recent", "regular", "reign", "remember", "sentence",
    "separate", "special", "straight", "strange", "strength", "suppose",
    "surprise", "therefore", "though", "although", "thought", "through",
    "various", "weight", "woman", "women",
)


@dataclass(frozen=True)
class WordTier:
    key: str
    label: str
    words: tuple[str, ...]


# Progression order - a child on a later tier is assumed to have already
# mastered every word in every tier before it.
TIERS: tuple[WordTier, ...] = (
    WordTier("first100", "First 100 High Frequency Words", FIRST_100),
    WordTier("next200", "Next 200 High Frequency Words", NEXT_200),
    WordTier("year34", "Year 3 and 4 Word List", YEAR_3_4),
)

TIERS_BY_KEY = {tier.key: tier for tier in TIERS}


def tier_index(tier_key: str) -> int:
    for i, tier in enumerate(TIERS):
        if tier.key == tier_key:
            return i
    raise ValueError(f"Unknown tier: {tier_key}")
