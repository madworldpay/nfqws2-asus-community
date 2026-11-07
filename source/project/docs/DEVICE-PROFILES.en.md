# Device profiles · beta

Open **Devices · beta** in the panel. **Common** is the default: the ordinary configuration handles every device. Use **Per device** only when selected devices need different strategies. DNS remains shared.

1. Add devices from the router's local DHCP/neighbour observations, or enter an IP or MAC manually. A known entry does not prove the device is online. MAC assignments follow complete, unambiguous local observations; unavailable observations use the common fallback. A fixed IP entry is tied to that IP.
2. Capture your current strategy in the library, or import a complete JSON export or a profile from the signed catalog. Each copy has its own lists, Lua, blobs and auto.list. Review the source before granting Lua trust. Import does not change the normal configuration or SmartDNS.
3. Create profile cards, select a strategy and devices, then drag cards or use Move up/down. The first enabled card containing a device wins. Devices not selected use the ordinary strategy; existing global exclusions take precedence.
4. Review and save the draft, then explicitly press **Apply saved mode**. Saving alone changes no traffic. Choose whether the NFQWS2 service should run afterwards. The operation continues when the tab closes.
5. Check the operation's phase and outcome, then verify the actual services on the selected device. Repeat the same Detector tests before/after under comparable conditions; its results do not guarantee another provider's connectivity. If activation fails, the job reports the original cause and whether restoration was verified; copy this information when asking for help.

The beta supports up to128 devices,16 ordered cards,8 saved strategies and4 distinct additional strategy processes. Duplicate cards using the same saved strategy share one process. Additional engines consume RAM; importing a profile does not guarantee that every router has enough memory to run it. IPv6 capture follows the existing global IPv6 setting.

To disable per-device routing, save and apply **Common**. Before updating the package while this beta is active, apply Common first. Saved library entries and drafts are kept; verify the service and chosen mode after the update.
