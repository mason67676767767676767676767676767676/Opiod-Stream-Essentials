from pathlib import Path

root = Path(".")
src = root / "src/main/java/com/ninestyle"

# Use Minecraft's built-in font. The bundled project references a bubbly.ttf
# that was never included, which causes missing-glyph boxes on some clients.
draw = src / "Draw.java"
s = draw.read_text()
s = s.replace("import net.minecraft.text.Style;\n", "")
s = s.replace("import net.minecraft.text.StyleSpriteSource;\n", "")
s = s.replace("import net.minecraft.util.Identifier;\n", "")
s = s.replace('''    // If this line fails to compile on your mappings, replace with: Style.EMPTY (no custom font).
    private static final Style BUBBLY =
            Style.EMPTY.withFont(new StyleSpriteSource.Font(Identifier.of("ninestyle", "bubbly")));

    public static Text t(String s) {
        return Text.literal(s).setStyle(BUBBLY);
    }''','''    // Use the vanilla font so every label is readable even when no custom TTF is installed.
    public static Text t(String s) {
        return Text.literal(s);
    }''')
draw.write_text(s)

# Slow automatic balance polling down and guard against overlapping /bal requests.
tracker = src / "BalanceTracker.java"
tracker.write_text("""package com.ninestyle;

import net.minecraft.client.MinecraftClient;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Periodically runs /bal, reads the chat reply, and tracks balance changes. */
public final class BalanceTracker {
    private BalanceTracker() {}

    private static final Pattern MONEY =
            Pattern.compile("\\$\\s*([\\d,]+(?:\\.\\d+)?)\\s*([kKmMbBtT])?(?![A-Za-z])");

    public static double balance = Double.NaN;
    public static double previous = Double.NaN;
    public static double lastChange = Double.NaN;

    private static long awaitUntil = 0;
    private static boolean requestPending = false;
    private static int sinceJoin = 0;
    private static int sinceCheck = 0;

    public static boolean hasData() {
        return !Double.isNaN(balance);
    }

    public static void tick(MinecraftClient mc) {
        if (mc.player == null || mc.getNetworkHandler() == null) {
            sinceJoin = 0;
            sinceCheck = 0;
            requestPending = false;
            awaitUntil = 0;
            return;
        }

        Config cfg = Config.get();
        if (!cfg.hudEnabled) return;

        long now = System.currentTimeMillis();
        if (requestPending && now > awaitUntil) {
            // The server did not return a parseable balance; allow a later retry.
            requestPending = false;
        }

        sinceJoin++;
        if (sinceJoin < 80 || requestPending) return;

        sinceCheck++;
        if (sinceCheck >= cfg.checkSeconds * 20) {
            sinceCheck = 0;
            requestPending = true;
            awaitUntil = now + 10000;
            mc.getNetworkHandler().sendChatCommand("bal");
        }
    }

    /** @return true if this message was our /bal reply (and should be hidden, if enabled). */
    public static boolean onMessage(String msg, boolean overlay) {
        if (overlay || !requestPending || System.currentTimeMillis() > awaitUntil) return false;

        String low = msg.toLowerCase();
        if (!low.contains("balance")) return false;
        if (low.contains("paid") || low.contains("received") || low.contains("sent")) return false;

        Matcher m = MONEY.matcher(msg);
        if (!m.find()) return false;

        double v;
        try {
            v = Double.parseDouble(m.group(1).replace(",", ""));
        } catch (NumberFormatException e) {
            return false;
        }

        String suf = m.group(2);
        if (suf != null) {
            switch (Character.toLowerCase(suf.charAt(0))) {
                case 'k' -> v *= 1e3;
                case 'm' -> v *= 1e6;
                case 'b' -> v *= 1e9;
                case 't' -> v *= 1e12;
                default -> {}
            }
        }

        if (Double.isNaN(balance)) {
            balance = v;
        } else if (v != balance) {
            previous = balance;
            lastChange = v - balance;
            balance = v;
        }

        requestPending = false;
        awaitUntil = 0;
        return Config.get().hideReply;
    }
}
""")

config = src / "Config.java"
s = config.read_text().replace("public int checkSeconds = 10;", "public int checkSeconds = 60;")
s = s.replace("if (checkSeconds < 5) checkSeconds = 5;", "if (checkSeconds < 30) checkSeconds = 60;")
config.write_text(s)

palette = src / "Palette.java"
s = palette.read_text().replace("public static final int[] INTERVALS = {5, 10, 15, 30, 60};",
                                "public static final int[] INTERVALS = {30, 60, 120, 300};")
palette.write_text(s)

# Bump the release number for the corrected build.
props = root / "gradle.properties"
s = props.read_text().replace("mod_version=1.0.0", "mod_version=1.0.1")
props.write_text(s)
