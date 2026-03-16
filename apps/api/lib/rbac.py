PERMISSIONS: dict[str, set[str]] = {
    "organizer": {
        "event:create", "event:update", "event:show", "event:list", "event:clone",
        "signup:confirm", "signup:cancel", "signup:list", "signup:show",
        "notify:send",
        "payment:link", "payment:status", "payment:refund",
        "list:events", "list:signups", "list:waitlist",
        "show:context",
    },
    "participant": {
        "signup:confirm", "signup:cancel", "signup:list", "signup:show",
        "payment:link", "payment:status",
        "list:events", "list:signups", "list:waitlist",
        "show:context",
    },
}


def check_rbac(role: str, key: str) -> bool:
    return key in PERMISSIONS.get(role, set())
