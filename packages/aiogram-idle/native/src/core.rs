//! Clock-free, I/O-free scalar domain decisions shared by Python entry points.
use sha2::{Digest, Sha256};

pub const PHASES: &[&str] = &[
    "disarmed",
    "active",
    "prompt_pending",
    "prompted",
    "delivery_unknown",
    "resuming",
    "abandoning",
    "restoring",
    "effect_unknown",
    "quarantined",
];
pub const TRIGGERS: &[&str] = &[
    "enter",
    "touch",
    "clear",
    "due_prompt",
    "due_restore",
    "shown",
    "unknown_delivery",
    "continue",
    "cancel",
    "timeout",
    "finish",
    "unknown_effect",
    "exhausted",
];
pub fn transition(phase: &str, trigger: &str) -> Option<&'static str> {
    if !PHASES.contains(&phase) || !TRIGGERS.contains(&trigger) {
        return None;
    }
    match trigger {
        "clear" => return Some("disarmed"),
        "exhausted" => return Some("quarantined"),
        "unknown_effect" => return Some("effect_unknown"),
        "enter" | "touch"
            if ["disarmed", "active", "prompted", "delivery_unknown"].contains(&phase) =>
        {
            return Some("active")
        }
        _ => (),
    }
    match (phase, trigger) {
        ("active", "due_prompt") => Some("prompt_pending"),
        ("active", "due_restore") => Some("restoring"),
        ("prompt_pending", "shown") => Some("prompted"),
        ("prompt_pending", "unknown_delivery") => Some("delivery_unknown"),
        ("prompted" | "delivery_unknown", "continue") => Some("resuming"),
        ("prompted" | "delivery_unknown", "cancel") | ("prompted", "timeout") => Some("abandoning"),
        ("resuming", "finish") => Some("active"),
        ("abandoning" | "restoring", "finish") => Some("disarmed"),
        _ => None,
    }
}
pub fn digest(raw: &str) -> String {
    format!("{:x}", Sha256::digest(raw.as_bytes()))
}
pub fn receipt(existing: Option<&str>, digest: &str, count: usize, limit: usize) -> &'static str {
    match existing {
        Some(value) if value != digest => "conflict",
        Some(_) => "duplicate",
        None if count >= limit => "capacity",
        None => "admit",
    }
}
pub fn activity(
    actual: Option<(&str, &str, &str, f64)>,
    expected: (&str, &str, &str),
    now: f64,
) -> Option<&'static str> {
    match actual {
        None => Some("conflict"),
        Some((sid, aid, revision, _)) if (sid, aid, revision) != expected => Some("conflict"),
        Some((_, _, _, expiry)) if expiry <= now => Some("expired"),
        _ => None,
    }
}
pub fn session(
    actual: Option<(&str, &str, f64)>,
    expected: Option<(&str, &str)>,
    now: f64,
) -> Option<&'static str> {
    match actual {
        None => Some("expired"),
        Some((_, _, expiry)) if expiry <= now => Some("expired"),
        Some((sid, revision, _)) if expected.is_some_and(|guard| guard != (sid, revision)) => {
            Some("conflict")
        }
        _ => None,
    }
}
pub fn claim(
    actual: Option<(&str, &str, f64)>,
    expected: (&str, &str),
    now: f64,
) -> Option<&'static str> {
    match actual {
        Some((token, generation, lease)) if (token, generation) == expected && lease > now => None,
        _ => Some("ownership"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn all_lifecycle_inputs_are_total() {
        for phase in PHASES {
            for trigger in TRIGGERS {
                let value = transition(phase, trigger);
                assert!(value.is_none() || PHASES.contains(&value.unwrap()));
            }
        }
        assert_eq!(transition("bogus", "clear"), None);
        assert_eq!(transition("active", "bogus"), None);
        assert_eq!(transition("prompted", "continue"), Some("resuming"));
    }
    #[test]
    fn duplicate_wins_over_capacity() {
        assert_eq!(receipt(Some("a"), "a", 1, 1), "duplicate");
        assert_eq!(receipt(Some("a"), "b", 1, 1), "conflict");
        assert_eq!(receipt(None, "b", 1, 1), "capacity");
    }
    #[test]
    fn guards_require_exact_live_generation() {
        assert_eq!(
            activity(Some(("s", "a", "2", 20.0)), ("s", "a", "2"), 19.0),
            None
        );
        assert_eq!(
            activity(Some(("s", "a", "2", 20.0)), ("s", "a", "1"), 19.0),
            Some("conflict")
        );
        assert_eq!(
            activity(Some(("s", "a", "2", 20.0)), ("s", "a", "2"), 20.0),
            Some("expired")
        );
        assert_eq!(
            claim(Some(("t", "1", 10.0)), ("t", "1"), 10.0),
            Some("ownership")
        );
        assert_eq!(session(Some(("s", "1", 10.0)), Some(("s", "1")), 9.0), None);
    }
    #[test]
    fn exact_supplied_bytes_only() {
        assert_eq!(
            digest(""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_ne!(digest("1"), digest("1.0"));
        assert_ne!(digest("\"é\""), digest("\"\\u00e9\""));
    }
}
