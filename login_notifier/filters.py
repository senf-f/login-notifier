def should_notify(username, whitelist, blacklist):
    """A non-empty whitelist takes precedence over the blacklist."""
    if whitelist:
        return username in whitelist
    return username not in blacklist
