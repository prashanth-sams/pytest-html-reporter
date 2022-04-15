import random
import string


def get_random_string(sz=10):
    return ''.join(random.choice(string.ascii_letters) for x in range(sz))

def get_random_number(limit=10000):
    return random.randint(0, limit)