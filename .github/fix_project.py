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
    meta.write_text(json.dumps(data, indent=2) + "\n")


# Rebrand the installed client and its visible HUD as VØID.
import json
meta = root / "src/main/resources/fabric.mod.json"
if meta.exists():
    data = json.loads(meta.read_text())
    data["name"] = "VØID"
    data["description"] = "VØID — modular streamer essentials"
    meta.write_text(json.dumps(data, indent=2) + "\n")

hud = src / "BalanceHud.java"
if hud.exists():
    s = hud.read_text().replace('Owner: @9ugh @Jittrclick', 'VØID  //  BALANCE TRACKER')
    hud.write_text(s)

# Release number for the VØID-branded build.
props = root / "gradle.properties"
if props.exists():
    s = props.read_text().replace("mod_version=1.0.3", "mod_version=1.0.4")
    props.write_text(s)
if meta.exists():
    data = json.loads(meta.read_text())
    data["version"] = "1.0.4"
    meta.write_text(json.dumps(data, indent=2) + "\n")


# VØID balance tracker reliability update:
# - request /bal shortly after joining and then on the configured interval
# - accept common server formats with or without a currency symbol
# - don't require the literal word "balance" if a /bal reply contains a money amount
tracker = src / "BalanceTracker.java"
tracker.write_text(r"""package com.ninestyle;

import net.minecraft.client.MinecraftClient;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Polls /bal and tracks the session baseline, current balance, and net change. */
public final class BalanceTracker {
    private BalanceTracker() {}

    private static final Pattern MONEY = Pattern.compile(
        "(?i)\\$?\\s*([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*([kmbt])?(?![a-z])"
    );
    private static final Pattern LABELED = Pattern.compile(
        "(?i)(?:balance|bal(?:ance)?)\\D{0,24}\\$?\\s*([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*([kmbt])?"
    );

    public static double balance = Double.NaN;
    public static double startingBalance = Double.NaN;
    public static double previous = Double.NaN;
    public static double lastChange = Double.NaN;

    private static long nextRequestAt = 0L;
    private static long awaitUntil = 0L;
    private static boolean requestPending = false;
    private static int joinTicks = 0;

    public static boolean hasData() { return !Double.isNaN(balance); }

    public static void tick(MinecraftClient mc) {
        if (mc.player == null || mc.getNetworkHandler() == null) {
            joinTicks = 0;
            requestPending = false;
            awaitUntil = 0L;
            nextRequestAt = 0L;
            balance = startingBalance = previous = lastChange = Double.NaN;
            return;
        }
        Config cfg = Config.get();
        if (!cfg.hudEnabled) return;

        if (joinTicks < 40) {
            joinTicks++;
            if (joinTicks < 40) return;
        }

        long now = System.currentTimeMillis();
        if (requestPending && now <= awaitUntil) return;
        if (now < nextRequestAt) return;

        requestPending = true;
        awaitUntil = now + 12000L;
        nextRequestAt = now + Math.max(30, cfg.checkSeconds) * 1000L;
        mc.getNetworkHandler().sendChatCommand("bal");
    }

    public static boolean onMessage(String msg, boolean overlay) {
        if (overlay || !requestPending || System.currentTimeMillis() > awaitUntil) return false;
        String low = msg.toLowerCase();
        if (low.contains("paid") || low.contains("received") || low.contains("sent")
                || low.contains("transfer") || low.contains("purchase")) return false;

        Matcher m = LABELED.matcher(msg);
        if (!m.find()) {
            // Some economy plugins reply with just "$12,345" after /bal.
            m = MONEY.matcher(msg);
            if (!m.find() || (!msg.contains("$") && !low.contains("bal"))) return false;
        }

        double value;
        try {
            value = Double.parseDouble(m.group(1).replace(",", ""));
            String suffix = m.group(2);
            if (suffix != null) {
                switch (Character.toLowerCase(suffix.charAt(0))) {
                    case 'k' -> value *= 1_000d;
                    case 'm' -> value *= 1_000_000d;
                    case 'b' -> value *= 1_000_000_000d;
                    case 't' -> value *= 1_000_000_000_000d;
                    default -> {}
                }
            }
        } catch (RuntimeException ex) {
            return false;
        }

        if (Double.isNaN(startingBalance)) {
            startingBalance = value;
            balance = value;
            previous = value;
            lastChange = 0d;
        } else {
            previous = balance;
            balance = value;
            lastChange = balance - previous;
        }

        requestPending = false;
        awaitUntil = 0L;
        return Config.get().hideReply;
    }
}
""")

# Ensure the settings screen is reachable with /opiod and visibly branded VØID.
client = src / "NineStyleClient.java"
if client.exists():
    s = client.read_text().replace('literal("9ugh")', 'literal("opiod")')
    s = s.replace('// /9ugh opens the theme + HUD settings', '// /opiod opens VØID settings')
    client.write_text(s)

screen = src / "SettingsScreen.java"
if screen.exists():
    s = screen.read_text().replace('Text.literal("9ugh Style")', 'Text.literal("VØID")')
    s = s.replace('"9ugh Style"', '"VØID"')
    s = s.replace('"Balance Tracker  (/bal)"', '"VØID BALANCE TRACKER  (/bal)"')
    screen.write_text(s)


# VØID redesigned settings window: sidebar navigation and larger modular panels.
screen = src / "SettingsScreen.java"
screen.write_text(r'''package com.ninestyle;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;
import java.util.HashMap;
import java.util.Map;

public class SettingsScreen extends Screen {
    private final Map<String, Float> hover = new HashMap<>();
    private boolean prevDown, justPressed, blocked;
    private int mx, my;
    private String page = "Overview";

    private static final int BG = 0xE90A0D16;
    private static final int PANEL = 0xE9161B28;
    private static final int PANEL2 = 0xE91D2433;
    private static final int ACCENT = 0xFF9B7BFF;
    private static final int CYAN = 0xFF65DDF2;
    private static final int WHITE = 0xFFF1F2FA;
    private static final int MUTED = 0xFF929AAF;

    public SettingsScreen() { super(Text.literal("VØID")); }

    @Override protected void init() { prevDown = down(); }

    private static boolean down() {
        MinecraftClient mc = MinecraftClient.getInstance();
        return GLFW.glfwGetMouseButton(mc.getWindow().getHandle(), GLFW.GLFW_MOUSE_BUTTON_LEFT) == GLFW.GLFW_PRESS;
    }

    @Override public void render(DrawContext c, int mouseX, int mouseY, float delta) {
        mx = mouseX; my = mouseY;
        boolean isDown = down();
        justPressed = isDown && !prevDown;
        prevDown = isDown;

        c.fill(0, 0, width, height, 0x9903070D);
        int pw = Math.min(650, width - 28), ph = Math.min(390, height - 24);
        int px = (width - pw) / 2, py = (height - ph) / 2;
        Draw.round(c, px, py, pw, ph, 13, 0xFF66518F);
        Draw.round(c, px + 1, py + 1, pw - 2, ph - 2, 12, BG);

        // Sidebar
        Draw.round(c, px + 8, py + 8, 148, ph - 16, 9, PANEL);
        Draw.text(c, "VØID", px + 22, py + 22, ACCENT);
        Draw.text(c, "STREAMER ESSENTIALS", px + 22, py + 36, MUTED);
        String[] nav = {"Overview", "Balance", "HUD Layout", "Themes", "Payments", "Auctions"};
        int ny = py + 67;
        for (int i = 0; i < nav.length; i++) {
            final String name = nav[i];
            int by = ny + i * 34;
            boolean selected = page.equals(name);
            if (selected) Draw.round(c, px + 16, by - 5, 132, 27, 6, 0xFF342B50);
            if (selected) Draw.round(c, px + 16, by - 5, 3, 27, 2, ACCENT);
            boolean over = mx >= px + 16 && mx < px + 148 && my >= by - 5 && my < by + 22;
            Draw.text(c, name, px + 27, by + 3, selected ? WHITE : (over ? CYAN : MUTED));
            if (over && justPressed) page = name;
        }
        Draw.text(c, "CLIENT BUILD  1.0.5", px + 20, py + ph - 26, MUTED);

        int cx = px + 174, cw = pw - 190;
        Draw.text(c, page.toUpperCase(), cx, py + 20, WHITE);
        Draw.text(c, "Customize your stream setup", cx, py + 36, MUTED);
        blocked = false;

        switch (page) {
            case "Overview" -> overview(c, cx, py, cw);
            case "Balance" -> balance(c, cx, py, cw);
            case "HUD Layout" -> hud(c, cx, py, cw);
            case "Themes" -> themes(c, cx, py, cw);
            case "Payments" -> unavailable(c, cx, py, cw, "PAYMENT ACTIVITY", "Payment event tracking is not connected yet.");
            case "Auctions" -> unavailable(c, cx, py, cw, "AUCTION TRACKER", "Auction tracking is not connected yet.");
        }
        Draw.text(c, "ESC  Close settings", px + pw - 130, py + ph - 20, MUTED);
    }

    private void overview(DrawContext c, int x, int y, int w) {
        card(c, x, y + 62, w, 88, "BALANCE TRACKER", "Tracks your change from your first successful /bal");
        String net = Double.isNaN(BalanceTracker.lastChange) ? "Waiting for /bal" : MoneyFmt.signed(BalanceTracker.balance - BalanceTracker.startingBalance);
        Draw.text(c, net, x + 14, y + 105, CYAN);
        card(c, x, y + 160, (w - 10) / 2, 78, "HUD STATUS", Config.get().hudEnabled ? "Enabled" : "Disabled");
        card(c, x + (w - 10) / 2 + 10, y + 160, (w - 10) / 2, 78, "ACTIVE THEME", Theme.of(Config.get().theme).label);
        Draw.text(c, "Choose a section on the left to customize VØID.", x, y + 265, MUTED);
    }

    private void balance(DrawContext c, int x, int y, int w) {
        Config cfg = Config.get();
        card(c, x, y + 62, w, 66, "SESSION CHANGE", Double.isNaN(BalanceTracker.startingBalance) ? "Waiting for first /bal response" : MoneyFmt.signed(BalanceTracker.balance - BalanceTracker.startingBalance));
        card(c, x, y + 138, w, 58, "STARTING BALANCE", Double.isNaN(BalanceTracker.startingBalance) ? "--" : MoneyFmt.compact(BalanceTracker.startingBalance));
        card(c, x, y + 206, w, 58, "CURRENT BALANCE", Double.isNaN(BalanceTracker.balance) ? "--" : MoneyFmt.compact(BalanceTracker.balance));
        button(c, "interval", x, y + 282, 190, 30, "Poll every " + cfg.checkSeconds + "s", () -> {
            int[] a = Palette.INTERVALS; int i = 0;
            for (int j = 0; j < a.length; j++) if (a[j] == cfg.checkSeconds) i = j;
            cfg.checkSeconds = a[(i + 1) % a.length]; Config.save();
        });
        button(c, "hide", x + 202, y + 282, 190, 30, "Hide /bal reply: " + (cfg.hideReply ? "On" : "Off"), () -> { cfg.hideReply = !cfg.hideReply; Config.save(); });
    }

    private void hud(DrawContext c, int x, int y, int w) {
        Config cfg = Config.get();
        button(c, "toggle", x, y + 66, 190, 32, "HUD: " + (cfg.hudEnabled ? "On" : "Off"), () -> { cfg.hudEnabled = !cfg.hudEnabled; Config.save(); });
        button(c, "bg", x + 202, y + 66, 190, 32, "Panel: " + Palette.HUD_BG_NAMES[cfg.hudBg], () -> { cfg.hudBg = (cfg.hudBg + 1) % Palette.HUD_BG.length; Config.save(); });
        button(c, "txt", x, y + 110, 190, 32, "Accent: " + Palette.HUD_TEXT_NAMES[cfg.hudText], () -> { cfg.hudText = (cfg.hudText + 1) % Palette.HUD_TEXT.length; Config.save(); });
        button(c, "opacity", x + 202, y + 110, 190, 32, "Opacity: " + Palette.OPACITY_PCT[cfg.hudOpacity] + "%", () -> { cfg.hudOpacity = (cfg.hudOpacity + 1) % Palette.OPACITY_PCT.length; Config.save(); });
        button(c, "reset", x, y + 154, 190, 32, "Reset position", () -> { cfg.hudX = 8; cfg.hudY = 8; Config.save(); });
        Draw.text(c, "Drag the HUD preview to reposition it.", x, y + 210, MUTED);
        int[] sz = BalanceHud.size(!BalanceTracker.hasData());
        BalanceHud.draw(c, Math.min(x + 8, width - sz[0] - 8), y + 245, !BalanceTracker.hasData());
    }

    private void themes(DrawContext c, int x, int y, int w) {
        Theme[] all = Theme.values();
        for (int i = 0; i < all.length; i++) {
            int col = i % 2, row = i / 2;
            int bx = x + col * ((w - 10) / 2 + 10), by = y + 66 + row * 48;
            final int index = i;
            button(c, "theme" + i, bx, by, (w - 10) / 2, 36, (Config.get().theme == i ? "✓  " : "") + all[i].label, () -> { Config.get().theme = index; Config.save(); });
        }
    }

    private void unavailable(DrawContext c, int x, int y, int w, String heading, String desc) {
        card(c, x, y + 72, w, 105, heading, desc);
        Draw.text(c, "This section is a placeholder, not an active tracker.", x + 12, y + 145, MUTED);
    }

    private void card(DrawContext c, int x, int y, int w, int h, String title, String value) {
        Draw.round(c, x, y, w, h, 8, PANEL);
        Draw.text(c, title, x + 12, y + 12, MUTED);
        Draw.text(c, value, x + 12, y + 34, WHITE);
    }

    private void button(DrawContext c, String id, int x, int y, int w, int h, String label, Runnable action) {
        boolean over = mx >= x && mx < x + w && my >= y && my < y + h;
        Draw.round(c, x, y, w, h, 7, over ? 0xFF3C3158 : PANEL2);
        Draw.round(c, x, y, 3, h, 2, over ? CYAN : ACCENT);
        Draw.text(c, label, x + 12, y + (h - 9) / 2, WHITE);
        if (over && justPressed) action.run();
    }

    @Override public boolean shouldPause() { return false; }
}
''')
