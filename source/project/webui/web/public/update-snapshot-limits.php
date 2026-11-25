<?php
/** Byte budgets for owner settings, history and the protected backup index. */
final class NfqwsUpdateSnapshotLimits
{
    public const BYTES=67108864;
    public const JSON=2097152;

    // Payload, saved migration, quarantined migration and new defaults each
    // allow up to 512 entries. The remainder covers package metadata and the
    // rollback's private files, with the existing byte limit still enforced.
    public const ASUS_ROLLBACK_INDEX_FILES=4*512+32;
}
