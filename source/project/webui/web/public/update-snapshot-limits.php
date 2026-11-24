<?php
/** Existing settings plus eight saved strategies and the stock resource copy. */
final class NfqwsUpdateSnapshotLimits
{
    public const FILES=4096;
    public const BYTES=67108864;
    public const JSON=2097152;

    // Payload, saved migration, quarantined migration and new defaults each
    // allow up to 512 entries. The remainder covers package metadata and the
    // rollback's private files, with the existing byte limit still enforced.
    public const ASUS_ROLLBACK_INDEX_FILES=4*512+32;
}
