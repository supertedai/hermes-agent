# Options

1. Fix the root component/render failure and add a DOM regression test. Chosen direction; preserves Markdown semantics and existing fallback safety.
2. Remove the fallback or force raw text through a different renderer. Rejected: hides failures and regresses the safety/performance guard.
3. Add CSS to make the fallback look like Markdown. Rejected: markers would remain literal and the underlying render path would still be broken.
4. Replace Streamdown wholesale. Rejected until the exact failure proves the dependency path cannot be repaired locally; excessive blast radius.
