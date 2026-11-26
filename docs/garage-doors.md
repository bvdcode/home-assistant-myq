# Garage door states and polling

Use the cover entity to open and close the door. For Alarmo, add the **Door open**
binary sensor in the **Sensors** tab. Its device class is `garage_door`. It is
off when MyQ confirms the door is closed and on for other known positions,
including while the door is moving. Unknown states stay unknown. An offline
or missing door is unavailable.

Home Assistant polls MyQ every two minutes and refreshes the list of accounts
every 15 minutes. The cover and sensors share those requests. A change made
outside Home Assistant can take up to two minutes to appear.

## After an open or close command

When MyQ accepts an open command for a closed door, the cover immediately shows
**Opening**. Closing an open door works the same way. The cover keeps that
status while MyQ reports the starting position, for up to 60 seconds. Once
MyQ reports a different state, the cover follows subsequent updates, including
a reversal. Sensors always show confirmed MyQ data.

The first status check runs one second after the command. The next checks are
two, three, four and then five seconds apart. Checks continue every five
seconds for at least 30 seconds from the command, even if the door reaches
its target earlier. If the door has yet to reach its target, checks continue
for up to 60 seconds. A new command restarts this schedule for that door.

Regular polling resumes when tracking finishes or the door becomes unavailable.
After failed background updates, retries wait four, eight and then 15 minutes.
MyQ can request a longer delay. A successful update restores the usual interval.
If you disable polling in Home Assistant's system options, commands leave the
last confirmed state on screen until you request a manual update.

## Opener settings

Supported settings appear under **Configuration** on the opener’s device page.

- **Remote control lockout** enables or disables remote controls. The existing
  **Vacation mode** sensor reports the mode independently.
- **Auto-close timer** sets the delay from 1 to 99 minutes. Set it to 0 to turn
  automatic closing off.
- **Work light duration** accepts 90, 150, 210 or 270 seconds.
- **Motion-activated work light** controls whether motion turns on the light.
  The **Work light** binary sensor shows whether the lamp is currently on.

The integration checks supported settings at startup. It rereads settings every
12 hours and after a change from Home Assistant. Door movement uses a separate
polling schedule.
