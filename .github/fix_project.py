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
            Pattern.compile("\\\\$\\\\s*([\\\\d,]+(?:\\\\.\\\\d+)?)\\\\s*([kKmMbBtT])?(?![A-Za-z])");

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

# Keep the packaged Fabric metadata aligned with this patched release.
meta = root / "src/main/resources/fabric.mod.json"
if meta.exists():
    s = meta.read_text().replace('"version": "1.0.0"', '"version": "1.0.1"')
    meta.write_text(s)

# Show net gain/loss relative to the first successful /bal response this session.
tracker = src / "BalanceTracker.java"
s = tracker.read_text()
s = s.replace("public static double balance = Double.NaN;", "public static double balance = Double.NaN;\n    public static double startingBalance = Double.NaN;")
s = s.replace("            awaitUntil = 0;\n            return;", "            awaitUntil = 0;\n            balance = Double.NaN;\n            startingBalance = Double.NaN;\n            previous = Double.NaN;\n            lastChange = Double.NaN;\n            return;")
s = s.replace("        if (Double.isNaN(balance)) {\n            balance = v;", "        if (Double.isNaN(balance)) {\n            startingBalance = v;\n            balance = v;\n            lastChange = 0;")
tracker.write_text(s)

hud = src / "BalanceHud.java"
s = hud.read_text()
s = s.replace('double bal = preview ? 125450 : BalanceTracker.balance;', 'double bal = preview ? 2500 : (Double.isNaN(BalanceTracker.balance) || Double.isNaN(BalanceTracker.startingBalance) ? Double.NaN : BalanceTracker.balance - BalanceTracker.startingBalance);')
s = s.replace('String big = Double.isNaN(bal) ? "$--" : MoneyFmt.compact(bal);', 'String big = Double.isNaN(bal) ? "$--" : MoneyFmt.signed(bal);')
s = s.replace('Draw.width("YOUR BALANCE")', 'Draw.width("SINCE FIRST /BAL")')
s = s.replace('"YOUR BALANCE", x + PAD', '"SINCE FIRST /BAL", x + PAD')
s = s.replace('"Previous"', '"Starting"')
s = s.replace('double prev = preview ? 122950 : BalanceTracker.previous;', 'double prev = preview ? 122950 : BalanceTracker.startingBalance;')
s = s.replace('String p = Double.isNaN(prev) ? "--" : MoneyFmt.compact(prev);', 'String p = Double.isNaN(prev) ? "--" : MoneyFmt.compact(prev);')
s = s.replace('"Change"', '"Current"')
s = s.replace('String c = Double.isNaN(chg) ? "--" : MoneyFmt.signed(chg);', 'String c = Double.isNaN(BalanceTracker.balance) && !preview ? "--" : MoneyFmt.compact(preview ? 125450 : BalanceTracker.balance);')
hud.write_text(s)

# Color the main figure by total gain/loss from the session baseline.
hud = src / "BalanceHud.java"
s = hud.read_text().replace("(chg > 0 ? GREEN : (chg < 0 ? RED : GRAY))", "(bal > 0 ? GREEN : (bal < 0 ? RED : GRAY))")
hud.write_text(s)

# Use /opiod as the settings command.
client = src / "NineStyleClient.java"
s = client.read_text().replace('literal("9ugh")', 'literal("opiod")')
client.write_text(s)

# Version for this balance-baseline release.
props = root / "gradle.properties"
s = props.read_text().replace("mod_version=1.0.1", "mod_version=1.0.2")
props.write_text(s)
meta = root / "src/main/resources/fabric.mod.json"
if meta.exists():
    s = meta.read_text().replace('"version": "1.0.1"', '"version": "1.0.2"')
    meta.write_text(s)


# Replace the single HUD card with three individually separated translucent modules.
hud = src / "BalanceHud.java"
hud.write_text('''package com.ninestyle;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;

public final class BalanceHud {
    private BalanceHud() {}

    private static final int PAD = 7;
    private static final float BIG = 1.55f;
    private static final int GREEN = 0xFF5CFF9D, RED = 0xFFFF6B6B, GRAY = 0xFFA0A8B4;
    private static final String OWNER = "Owner: @9ugh @Jittrclick";

    private record Vals(String net, String starting, String current, int netColor) {}

    private static Vals vals(boolean preview) {
        double start = preview ? 122950 : BalanceTracker.startingBalance;
        double current = preview ? 125450 : BalanceTracker.balance;
        double net = preview ? current - start : (Double.isNaN(start) || Double.isNaN(current) ? Double.NaN : current - start);
        String n = Double.isNaN(net) ? "$--" : MoneyFmt.signed(net);
        String s = Double.isNaN(start) ? "$--" : MoneyFmt.compact(start);
        String c = Double.isNaN(current) ? "$--" : MoneyFmt.compact(current);
        int color = Double.isNaN(net) ? GRAY : (net > 0 ? GREEN : (net < 0 ? RED : GRAY));
        return new Vals(n, s, c, color);
    }

    public static int[] size(boolean preview) {
        Vals v = vals(preview);
        int bigW = (int) Math.ceil(Draw.width(v.net) * BIG);
        int statsW = Draw.width("Starting: " + v.starting) + 14;
        int ownerW = Draw.width(OWNER) + 14;
        int w = Math.max(132, Math.max(bigW + PAD * 2, Math.max(statsW, ownerW)) + PAD * 2);
        return new int[]{w, 119};
    }

    public static void render(DrawContext c) {
        MinecraftClient mc = MinecraftClient.getInstance();
        Config cfg = Config.get();
        if (!cfg.hudEnabled || mc.options.hudHidden) return;
        if (mc.currentScreen instanceof SettingsScreen) return;
        int[] s = size(false);
        int x = Math.min(cfg.hudX, Math.max(0, mc.getWindow().getScaledWidth() - s[0]));
        int y = Math.min(cfg.hudY, Math.max(0, mc.getWindow().getScaledHeight() - s[1]));
        draw(c, x, y, false);
    }

    public static void draw(DrawContext c, int x, int y, boolean preview) {
        Config cfg = Config.get();
        Vals v = vals(preview);
        int[] dimensions = size(preview);
        int w = dimensions[0];
        int alpha = (int) (255 * (Palette.OPACITY_PCT[cfg.hudOpacity] / 100f));
        int bg = (alpha << 24) | (Palette.HUD_BG[cfg.hudBg] & 0xFFFFFF);
        int accent = Palette.HUD_TEXT[cfg.hudText];
        int module1 = 43, module2 = 35, module3 = 25, gap = 5;

        // Each section is its own card, with a visible gap between modules.
        Draw.round(c, x, y, w, module1, 7, bg);
        Draw.text(c, "BALANCE CHANGE", x + PAD, y + 5, GRAY);
        c.getMatrices().pushMatrix();
        c.getMatrices().translate(x + PAD, y + 17);
        c.getMatrices().scale(BIG, BIG);
        Draw.text(c, v.net, 0, 0, v.netColor);
        c.getMatrices().popMatrix();
        Draw.round(c, x + w - 15, y + 8, 7, 7, 3, accent);

        int y2 = y + module1 + gap;
        Draw.round(c, x, y2, w, module2, 7, bg);
        Draw.text(c, "STARTING", x + PAD, y2 + 5, GRAY);
        Draw.text(c, v.starting, x + PAD, y2 + 17, 0xFFE6EAF0);
        Draw.text(c, "CURRENT", x + w / 2, y2 + 5, GRAY);
        Draw.text(c, v.current, x + w / 2, y2 + 17, accent);

        int y3 = y2 + module2 + gap;
        Draw.round(c, x, y3, w, module3, 7, bg);
        Draw.text(c, OWNER, x + PAD, y3 + 8, accent);
    }
}
''')

# Use a slightly transparent default; users can still change opacity in /opiod.
config = src / "Config.java"
s = config.read_text().replace("hudBg = 0, hudText = 1, hudOpacity = 2;", "hudBg = 0, hudText = 1, hudOpacity = 1;")
config.write_text(s)

# Version for the modular HUD release.
props = root / "gradle.properties"
s = props.read_text().replace("mod_version=1.0.2", "mod_version=1.0.3")
props.write_text(s)
meta = root / "src/main/resources/fabric.mod.json"
if meta.exists():
    s = meta.read_text().replace('"version": "1.0.2"', '"version": "1.0.3"')
    meta.write_text(s)


# Rebrand the mod in Fabric's installed-mod list and metadata.
import json
meta = root / "src/main/resources/fabric.mod.json"
if meta.exists():
    data = json.loads(meta.read_text())
    data["name"] = "Opiod Streamer Essentials"
    meta.write_text(json.dumps(data, indent=2) + "\\n")
