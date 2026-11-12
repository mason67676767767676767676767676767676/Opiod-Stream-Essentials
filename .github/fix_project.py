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


# VØID 1.0.5: full stream-dashboard UI, live payment ledger, and auction entrypoint.
import json

# Expand the theme system to the 18 presets shown in the supplied reference.
(src / "Theme.java").write_text(r'''package com.ninestyle;

public enum Theme {
    MIDNIGHT("Midnight",0xFF070B14,0xD91B2232,0xFF68D9F5,0xFFF3F7FF,0xFF9BAAC2),
    FROSTED("Frosted Glass",0xFF101827,0xD92A3547,0xFF65DDF2,0xFFF4FAFF,0xFFA6B9CA),
    NEBULA("Nebula",0xFF10091D,0xD927183A,0xFFB58AFF,0xFFFFF5FF,0xFFC3A8D8),
    GALAXY("Galaxy",0xFF080D20,0xD91A2450,0xFF8D9CFF,0xFFF2F4FF,0xFF9CA9D5),
    AURORA("Aurora",0xFF071A1B,0xD9163436,0xFF61E6C1,0xFFF0FFFC,0xFF9ACBC1),
    SUNSET("Sunset",0xFF21101A,0xD9362032,0xFFFF9B78,0xFFFFF5F0,0xFFD8A89B),
    OCEAN("Ocean",0xFF071B2A,0xD9153047,0xFF4FC3F7,0xFFEAF8FF,0xFF8FB4CC),
    PURPLE("Purple Dream",0xFF170D2A,0xD9261747,0xFFB388FF,0xFFF5EDFF,0xFFA797C9),
    PINK("Bubblegum",0xFF2B1025,0xD9411B39,0xFFFF8AD8,0xFFFFEEF9,0xFFD6A0C2),
    MINT("Mint",0xFF09231D,0xD914392E,0xFF5EEAA8,0xFFEAFFF5,0xFF8FC4AE),
    BLOOD("Blood Red",0xFF24090D,0xD93B1018,0xFFFF5A6A,0xFFFFEEEE,0xFFC99093),
    EMBER("Ember",0xFF241108,0xD9402411,0xFFFFA94D,0xFFFFF3E6,0xFFCFA680),
    ICE("Ice White",0xFF152331,0xD9DDEBF4,0xFF3AA8E0,0xFFF5FAFF,0xFF6B7F90),
    LAVENDER("Lavender",0xFF1D1730,0xD9332850,0xFFD5A7FF,0xFFFFF7FF,0xFFC2B0D7),
    MATRIX("Matrix",0xFF06150D,0xD9112B1A,0xFF65FF8A,0xFFEFFFF2,0xFF91C99C),
    GOLD("Gold",0xFF211B0A,0xD93B3014,0xFFFFD76A,0xFFFFF9E8,0xFFD1C08D),
    ROSE("Rose",0xFF25111B,0xD93D1F32,0xFFFF83A8,0xFFFFF2F6,0xFFD6A4B5),
    VOID("VØID",0xFF050711,0xD91B1B31,0xFF9B7BFF,0xFFF4F1FF,0xFFAAA2C9);

    public final String label;
    public final int bg, panel, accent, text, sub;
    Theme(String label,int bg,int panel,int accent,int text,int sub) {
        this.label=label; this.bg=bg; this.panel=panel; this.accent=accent; this.text=text; this.sub=sub;
    }
    public static Theme of(int i) { return values()[Math.floorMod(i, values().length)]; }
}
''')

# Persistent UI/tracker preferences.
config = src / "Config.java"
s = config.read_text()
s = s.replace("public int checkSeconds = 60;", "public int checkSeconds = 5;")
s = s.replace("public boolean hideReply = true;", "public boolean hideReply = true;\n    public boolean trackerEnabled = true;\n    public boolean glass = true;\n    public boolean customSky = true;\n    public boolean audioEnabled = true;\n    public int skyStyle = 0;")
s = s.replace("if (checkSeconds < 30) checkSeconds = 60;", "if (checkSeconds < 5) checkSeconds = 5;\n        skyStyle = Math.floorMod(skyStyle, 4);")
config.write_text(s)

palette = src / "Palette.java"
s = palette.read_text()
s = s.replace("public static final int[] OPACITY_PCT = {50, 70, 85, 100};", "public static final int[] OPACITY_PCT = {45, 55, 65, 75, 85, 95};")
s = s.replace("public static final int[] INTERVALS = {30, 60, 120, 300};", "public static final int[] INTERVALS = {5, 10, 15, 30, 60};")
palette.write_text(s)

# Event ledger: immediate chat payment events plus balance decreases discovered by /bal.
(src / "PaymentLedger.java").write_text(r'''package com.ninestyle;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class PaymentLedger {
    private PaymentLedger() {}
    public record Entry(String title, String detail, double amount, long at, boolean incoming, String source) {}
    private static final Deque<Entry> ITEMS = new ArrayDeque<>();
    private static final Pattern MONEY = Pattern.compile("(?i)\\$\\s*([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*([kmbt])?");
    private static String lastText = "";
    private static long lastAt = 0L;
    private static long lastOutgoingAt = 0L;
    private static double lastOutgoingAmount = 0d;

    public static synchronized List<Entry> entries() { return new ArrayList<>(ITEMS); }
    public static synchronized int count() { return ITEMS.size(); }

    public static synchronized void onMessage(String message, boolean overlay) {
        if (overlay || message == null) return;
        String low = message.toLowerCase(Locale.ROOT);
        if (!(low.contains("paid") || low.contains("received") || low.contains("sent you")
                || low.contains("transferred") || low.contains("purchased") || low.contains("payment"))) return;
        long now = System.currentTimeMillis();
        if (message.equals(lastText) && now - lastAt < 1800L) return;
        Matcher m = MONEY.matcher(message);
        if (!m.find()) return;
        double amount;
        try {
            amount = Double.parseDouble(m.group(1).replace(",", ""));
            String suffix = m.group(2);
            if (suffix != null) {
                switch (Character.toLowerCase(suffix.charAt(0))) {
                    case 'k' -> amount *= 1_000d;
                    case 'm' -> amount *= 1_000_000d;
                    case 'b' -> amount *= 1_000_000_000d;
                    case 't' -> amount *= 1_000_000_000_000d;
                    default -> {}
                }
            }
        } catch (RuntimeException ex) { return; }
        boolean incoming = low.contains("paid you") || low.contains("received") || low.contains("sent you");
        boolean outgoing = !incoming && (low.contains("you paid") || low.contains("you sent")
                || low.contains("transferred") || low.contains("purchased") || low.contains("payment"));
        if (!incoming && !outgoing) return;
        String who = "Player";
        Matcher name = Pattern.compile("([A-Za-z0-9_]{1,16})\\s+(?:has\\s+)?paid\\s+you", Pattern.CASE_INSENSITIVE).matcher(message);
        if (name.find()) who = name.group(1);
        else {
            Matcher from = Pattern.compile("(?i)from\\s+([A-Za-z0-9_]{1,16})").matcher(message);
            if (from.find()) who = from.group(1);
            else {
                Matcher to = Pattern.compile("(?i)to\\s+([A-Za-z0-9_]{1,16})").matcher(message);
                if (to.find()) who = to.group(1);
            }
        }
        lastText = message;
        lastAt = now;
        if (outgoing) {
            lastOutgoingAt = now;
            lastOutgoingAmount = amount;
            add(new Entry("Payment sent", "To " + who, -amount, now, false, "CHAT"));
        } else {
            add(new Entry("Payment received", "From " + who, amount, now, true, "CHAT"));
        }
    }

    public static synchronized void recordBalanceDecrease(double amount, double newBalance) {
        if (!(amount > 0d)) return;
        long now = System.currentTimeMillis();
        // If the chat already told us about this outgoing payment, don't duplicate it.
        if (now - lastOutgoingAt < 12000L
                && Math.abs(lastOutgoingAmount - amount) <= Math.max(1d, amount * 0.02d)) {
            lastOutgoingAt = 0L;
            lastOutgoingAmount = 0d;
            return;
        }
        add(new Entry("Balance decreased", "Balance check → " + MoneyFmt.compact(newBalance),
                -amount, now, false, "BALANCE"));
    }

    private static void add(Entry entry) {
        ITEMS.addFirst(entry);
        while (ITEMS.size() > 60) ITEMS.removeLast();
    }
}
''')

# Replace the polling logic: it works even when the on-screen HUD is hidden.
(src / "BalanceTracker.java").write_text(r'''package com.ninestyle;

import net.minecraft.client.MinecraftClient;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class BalanceTracker {
    private BalanceTracker() {}
    private static final Pattern LABELED = Pattern.compile(
        "(?i)(?:balance|bal)\\D{0,30}\\$?\\s*([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*([kmbt])?"
    );
    private static final Pattern MONEY = Pattern.compile(
        "(?i)\\$\\s*([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*([kmbt])?"
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
        if (!cfg.trackerEnabled) return;
        if (joinTicks < 40) {
            joinTicks++;
            if (joinTicks < 40) return;
        }
        long now = System.currentTimeMillis();
        if (requestPending && now <= awaitUntil) return;
        if (now < nextRequestAt) return;
        requestPending = true;
        awaitUntil = now + 12000L;
        nextRequestAt = now + Math.max(5, cfg.checkSeconds) * 1000L;
        mc.getNetworkHandler().sendChatCommand("bal");
    }

    public static boolean onMessage(String msg, boolean overlay) {
        if (overlay || !requestPending || System.currentTimeMillis() > awaitUntil || msg == null) return false;
        String low = msg.toLowerCase();
        if (low.contains("paid") || low.contains("received") || low.contains("sent")
                || low.contains("transfer") || low.contains("purchase")) return false;
        Matcher m = LABELED.matcher(msg);
        if (!m.find()) {
            m = MONEY.matcher(msg);
            if (!m.find()) return false;
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
        } catch (RuntimeException ex) { return false; }

        if (Double.isNaN(startingBalance)) {
            startingBalance = value;
            balance = value;
            previous = value;
            lastChange = 0d;
        } else {
            previous = balance;
            balance = value;
            lastChange = value - previous;
            if (value < previous) PaymentLedger.recordBalanceDecrease(previous - value, value);
        }
        requestPending = false;
        awaitUntil = 0L;
        return Config.get().hideReply;
    }
}
''')

# Apply theme colors and frosted-glass opacity to the in-game balance HUD.
hud = src / "BalanceHud.java"
s = hud.read_text()
s = s.replace("int alpha = (int) (255 * (Palette.OPACITY_PCT[cfg.hudOpacity] / 100f));\n        int bg = (alpha << 24) | (Palette.HUD_BG[cfg.hudBg] & 0xFFFFFF);\n        int accent = Palette.HUD_TEXT[cfg.hudText];",
'''Theme theme = Theme.of(cfg.theme);
        int alpha = (int) (255 * (Palette.OPACITY_PCT[cfg.hudOpacity] / 100f) * (cfg.glass ? 0.86f : 1f));
        int bg = (alpha << 24) | (theme.panel & 0xFFFFFF);
        int accent = theme.accent;''')
hud.write_text(s)

# Load the bundled auction mod's client initializer and keep /opiod as the settings command.
client = src / "NineStyleClient.java"
client.write_text(r'''package com.ninestyle;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandManager;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.minecraft.client.MinecraftClient;
import net.minecraft.util.Identifier;

public class NineStyleClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        Config.load();
        HudElementRegistry.addLast(Identifier.of("ninestyle", "balance"),
                (context, tickCounter) -> BalanceHud.render(context));
        ClientTickEvents.END_CLIENT_TICK.register(BalanceTracker::tick);
        ClientReceiveMessageEvents.ALLOW_GAME.register((message, overlay) -> {
            String text = message.getString();
            PaymentLedger.onMessage(text, overlay);
            return !BalanceTracker.onMessage(text, overlay);
        });
        ClientCommandRegistrationCallback.EVENT.register((dispatcher, registryAccess) -> {
            dispatcher.register(ClientCommandManager.literal("opiod").executes(ctx -> {
                MinecraftClient mc = MinecraftClient.getInstance();
                mc.send(() -> mc.setScreen(new SettingsScreen()));
                return 1;
            }));
            dispatcher.register(ClientCommandManager.literal("9ugh").executes(ctx -> {
                MinecraftClient mc = MinecraftClient.getInstance();
                mc.send(() -> mc.setScreen(new SettingsScreen()));
                return 1;
            }));
        });
    }
}
''')

# Merge the original auction module into this mod's Fabric client entrypoints.
meta = root / "src/main/resources/fabric.mod.json"
data = json.loads(meta.read_text())
data["name"] = "VØID Streamer Essentials"
data["description"] = "VØID — modular streamer dashboard, payment tracker and auctions"
eps = data.setdefault("entrypoints", {}).setdefault("client", [])
if "com.donutauction.DonutAuctionClient" not in eps:
    eps.append("com.donutauction.DonutAuctionClient")
data["version"] = "1.0.5"
meta.write_text(json.dumps(data, indent=2) + "\n")

props = root / "gradle.properties"
s = props.read_text()
import re
s = re.sub(r"(?m)^mod_version=.*$", "mod_version=1.0.5", s)
props.write_text(s)

# Full dashboard inspired by the uploaded reference video.
(src / "SettingsScreen.java").write_text(r'''package com.ninestyle;

import com.donutauction.Auction;
import com.donutauction.AuctionScreen;
import com.donutauction.DonutAuctionClient;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;
import java.util.List;
import java.util.Locale;

public class SettingsScreen extends Screen {
    private String page = "Tracker";
    private boolean prevDown, justPressed;
    private int mx, my;
    private long transitionAt = 0L;
    private static final String[] NAV = {"Tracker","Auction","HUD","Visuals","Appearance","Audio","Settings"};
    private static final String[] SKY = {"Nebula","Galaxy","Aurora","Sunset"};

    private int left, top, panelW, panelH, contentX, contentW;
    public SettingsScreen() { super(Text.literal("VØID Stream Essentials")); }

    @Override protected void init() { prevDown = down(); }

    private static boolean down() {
        MinecraftClient mc = MinecraftClient.getInstance();
        return GLFW.glfwGetMouseButton(mc.getWindow().getHandle(), GLFW.GLFW_MOUSE_BUTTON_LEFT) == GLFW.GLFW_PRESS;
    }

    private void changePage(String next) {
        if (!page.equals(next)) {
            page = next;
            transitionAt = System.currentTimeMillis();
        }
    }

    @Override public void render(DrawContext c, int mouseX, int mouseY, float delta) {
        mx = mouseX; my = mouseY;
        boolean isDown = down();
        justPressed = isDown && !prevDown;
        prevDown = isDown;
        Config cfg = Config.get();
        Theme th = Theme.of(cfg.theme);

        drawSpace(c, th);
        panelW = Math.min(790, width - 24);
        panelH = Math.min(450, height - 20);
        left = (width - panelW) / 2;
        top = (height - panelH) / 2;

        Draw.round(c, left - 1, top - 1, panelW + 2, panelH + 2, 15, 0xA85D6C9C);
        Draw.round(c, left, top, panelW, panelH, 14, 0xD00A101B);
        Draw.round(c, left + 1, top + 1, panelW - 2, panelH - 2, 13, 0xC80D1421);

        int sideW = 148;
        Draw.round(c, left + 8, top + 8, sideW, panelH - 16, 10, 0xC8172030);
        Draw.text(c, "VØID", left + 22, top + 18, th.accent);
        Draw.text(c, "STREAM ESSENTIALS", left + 22, top + 32, th.sub);
        Draw.round(c, left + 20, top + 50, 118, 1, 0, 0x665D7899);
        for (int i = 0; i < NAV.length; i++) {
            String name = NAV[i];
            int by = top + 65 + i * 37;
            boolean selected = page.equals(name);
            boolean over = inside(left + 15, by - 4, 132, 29);
            if (selected) {
                Draw.round(c, left + 15, by - 4, 132, 29, 7, 0x663E5274);
                Draw.round(c, left + 15, by - 4, 3, 29, 2, th.accent);
            } else if (over) Draw.round(c, left + 15, by - 4, 132, 29, 7, 0x443E5274);
            Draw.text(c, iconFor(name) + "  " + name, left + 25, by + 5, selected ? th.text : th.sub);
            if (over && justPressed) changePage(name);
        }
        Draw.round(c, left + 18, top + panelH - 49, 124, 1, 0, 0x665D7899);
        Draw.round(c, left + 21, top + panelH - 35, 8, 8, 4, cfg.trackerEnabled ? 0xFF55E6A5 : 0xFFFF7D87);
        Draw.text(c, cfg.trackerEnabled ? "Tracker online" : "Tracker paused", left + 35, top + panelH - 36, th.sub);
        Draw.text(c, "BUILD  1.0.5", left + 22, top + panelH - 20, 0xFF75839A);

        contentX = left + 170;
        contentW = panelW - 184;
        topBar(c, th);
        float progress = transitionAt == 0L ? 1f : Math.min(1f, (System.currentTimeMillis() - transitionAt) / 230f);
        float slide = (1f - ease(progress)) * 18f;
        c.getMatrices().pushMatrix();
        c.getMatrices().translate(slide, 0f);
        renderPage(c, th, cfg);
        c.getMatrices().popMatrix();
        if (progress < 1f) {
            int a = (int)((1f - progress) * 70f);
            c.fill(contentX, top + 65, left + panelW - 10, top + panelH - 10, (a << 24));
        }
    }

    private void drawSpace(DrawContext c, Theme th) {
        Config cfg = Config.get();
        c.fill(0, 0, width, height, th.bg);
        if (cfg.customSky) {
            int glow = switch (cfg.skyStyle) {
                case 1 -> 0x332B4DFF;
                case 2 -> 0x3328D6B0;
                case 3 -> 0x33FF8B52;
                default -> 0x334D2A82;
            };
            c.fill(0, 0, width, height, glow);
            for (int i = 0; i < 5; i++) {
                int x = Math.floorMod(i * 191 + 67, Math.max(1, width));
                int y = Math.floorMod(i * 127 + 33, Math.max(1, height));
                Draw.round(c, x - 75, y - 28, 150, 56, 28, (i % 2 == 0) ? glow : 0x182C6DAA);
            }
        }
        long tick = System.currentTimeMillis() / 850L;
        for (int i = 0; i < 105; i++) {
            int x = Math.floorMod(i * 137 + (int)(tick * (i % 3 + 1)), Math.max(1, width));
            int y = Math.floorMod(i * 83 + i * i * 3, Math.max(1, height));
            int alpha = 90 + (int)((Math.sin((tick + i) * 0.7) + 1) * 65);
            c.fill(x, y, x + 1, y + 1, (alpha << 24) | 0xDDEBFF);
        }
        c.fill(0, 0, width, height, 0x25030914);
    }

    private void topBar(DrawContext c, Theme th) {
        Draw.text(c, "FROSTS STREAM ESSENTIALS", contentX, top + 17, th.text);
        Draw.text(c, "Your stream, organized.", contentX, top + 32, th.sub);
        int pillX = left + panelW - 175;
        Draw.round(c, pillX, top + 13, 158, 24, 12, 0x88303C51);
        Draw.round(c, pillX + 9, top + 21, 6, 6, 3, 0xFF5CE6A8);
        Draw.text(c, MinecraftClient.getInstance().player == null ? "Offline" : "Live session", pillX + 22, top + 21, th.text);
        Draw.round(c, contentX, top + 52, contentW, 1, 0, 0x665D7899);
    }

    private void renderPage(DrawContext c, Theme th, Config cfg) {
        int y = top + 69;
        Draw.text(c, page.toUpperCase(Locale.ROOT), contentX, y, th.accent);
        Draw.text(c, subtitle(), contentX, y + 14, th.sub);
        switch (page) {
            case "Tracker" -> trackerPage(c, th, cfg, y + 34);
            case "Auction" -> auctionPage(c, th, y + 34);
            case "HUD" -> hudPage(c, th, cfg, y + 34);
            case "Visuals" -> visualsPage(c, th, cfg, y + 34);
            case "Appearance" -> appearancePage(c, th, cfg, y + 34);
            case "Audio" -> audioPage(c, th, cfg, y + 34);
            default -> settingsPage(c, th, cfg, y + 34);
        }
    }

    private String subtitle() {
        return switch (page) {
            case "Tracker" -> "Counts every payment and watches your balance";
            case "Auction" -> "Turn live viewer payments into auction bids";
            case "HUD" -> "Arrange the on-screen stream overlay";
            case "Visuals" -> "Choose the sky behind your dashboard";
            case "Appearance" -> "18 presets to make the client yours";
            case "Audio" -> "Auction sounds and stream feedback";
            default -> "Tracker behavior and client preferences";
        };
    }

    private void trackerPage(DrawContext c, Theme th, Config cfg, int y) {
        int half = (contentW - 12) / 2;
        card(c, contentX, y, contentW, 111, th, "LIVE PROFIT TRACKER", "Counts every payment from chat");
        button(c, "tracker", contentX + contentW - 78, y + 12, 64, 20,
                cfg.trackerEnabled ? "ON" : "OFF", th, () -> { cfg.trackerEnabled = !cfg.trackerEnabled; Config.save(); });
        double net = Double.isNaN(BalanceTracker.balance) || Double.isNaN(BalanceTracker.startingBalance)
                ? Double.NaN : BalanceTracker.balance - BalanceTracker.startingBalance;
        String profit = Double.isNaN(net) ? "Waiting for /bal" : MoneyFmt.signed(net);
        Draw.text(c, profit, contentX + 17, y + 47, Double.isNaN(net) ? th.sub : (net >= 0 ? 0xFF5DE6A2 : 0xFFFF788A));
        Draw.text(c, "Since first balance check", contentX + 18, y + 76, th.sub);
        card(c, contentX, y + 121, half, 56, th, "STARTING", Double.isNaN(BalanceTracker.startingBalance) ? "--" : MoneyFmt.compact(BalanceTracker.startingBalance));
        card(c, contentX + half + 12, y + 121, half, 56, th, "CURRENT", Double.isNaN(BalanceTracker.balance) ? "--" : MoneyFmt.compact(BalanceTracker.balance));
        int ly = y + 189;
        card(c, contentX, ly, contentW, 142, th, "RECENT ACTIVITY", PaymentLedger.count() + " events recorded this session");
        List<PaymentLedger.Entry> items = PaymentLedger.entries();
        if (items.isEmpty()) {
            Draw.text(c, "Payments and balance decreases will appear here.", contentX + 15, ly + 58, th.sub);
        } else {
            int count = Math.min(4, items.size());
            for (int i = 0; i < count; i++) {
                PaymentLedger.Entry e = items.get(i);
                int rowY = ly + 47 + i * 22;
                Draw.round(c, contentX + 14, rowY + 3, 6, 6, 3, e.incoming() ? 0xFF5DE6A2 : 0xFFFF788A);
                Draw.text(c, e.title(), contentX + 27, rowY, th.text);
                Draw.text(c, e.detail(), contentX + 160, rowY, th.sub);
                String amount = MoneyFmt.signed(e.amount());
                Draw.text(c, amount, contentX + contentW - 15 - Draw.width(amount), rowY, e.incoming() ? 0xFF5DE6A2 : 0xFFFF788A);
            }
        }
    }

    private void auctionPage(DrawContext c, Theme th, int y) {
        card(c, contentX, y, contentW, 105, th, "STREAM AUCTION", "Every detected viewer payment can become a bid");
        Auction a = DonutAuctionClient.auction;
        String status = a != null && a.active ? "Auction running" : "No active auction";
        Draw.text(c, status, contentX + 16, y + 47, a != null && a.active ? 0xFF5DE6A2 : th.sub);
        button(c, "openauction", contentX + contentW - 178, y + 38, 160, 28, "OPEN AUCTION", th,
                () -> MinecraftClient.getInstance().setScreen(new AuctionScreen()));
        card(c, contentX, y + 116, (contentW - 12) / 2, 74, th, "CURRENT ITEM",
                a == null ? "Waiting for auction" : a.itemName);
        card(c, contentX + (contentW - 12) / 2 + 12, y + 116, (contentW - 12) / 2, 74, th, "TOP BID",
                a == null ? "--" : MoneyFmt.compact(a.highBid));
        card(c, contentX, y + 200, contentW, 68, th, "AUCTION MODULE", "Original Donut Auction module is loaded and initialized inside VØID.");
    }

    private void hudPage(DrawContext c, Theme th, Config cfg, int y) {
        int half = (contentW - 12) / 2;
        card(c, contentX, y, contentW, 54, th, "HUD OVERLAY", "Live balance panel shown in-game");
        button(c, "hud", contentX + contentW - 90, y + 15, 76, 24, cfg.hudEnabled ? "ON" : "OFF", th,
                () -> { cfg.hudEnabled = !cfg.hudEnabled; Config.save(); });
        button(c, "glass", contentX, y + 65, half, 29, "Frosted glass: " + (cfg.glass ? "ON" : "OFF"), th,
                () -> { cfg.glass = !cfg.glass; Config.save(); });
        button(c, "opacity", contentX + half + 12, y + 65, half, 29,
                "Opacity: " + Palette.OPACITY_PCT[cfg.hudOpacity] + "%", th, () -> {
                    cfg.hudOpacity = (cfg.hudOpacity + 1) % Palette.OPACITY_PCT.length; Config.save();
                });
        button(c, "reset", contentX, y + 105, half, 29, "Reset HUD position", th, () -> {
            cfg.hudX = 8; cfg.hudY = 8; Config.save();
        });
        Draw.text(c, "HUD preview", contentX, y + 153, th.sub);
        BalanceHud.draw(c, contentX + 8, y + 174, !BalanceTracker.hasData());
    }

    private void visualsPage(DrawContext c, Theme th, Config cfg, int y) {
        card(c, contentX, y, contentW, 67, th, "CUSTOM SKY", "Nebula, galaxy, aurora and sunset backgrounds");
        button(c, "sky", contentX + contentW - 86, y + 20, 72, 25, cfg.customSky ? "ON" : "OFF", th,
                () -> { cfg.customSky = !cfg.customSky; Config.save(); });
        int gap = 9, bw = (contentW - gap * 3) / 4;
        for (int i = 0; i < SKY.length; i++) {
            final int idx = i;
            button(c, "sky" + i, contentX + i * (bw + gap), y + 81, bw, 43,
                    (cfg.skyStyle == i ? "✓ " : "") + SKY[i], th, () -> { cfg.skyStyle = idx; Config.save(); });
        }
        card(c, contentX, y + 138, contentW, 90, th, "STARFIELD", "Animated stars and a soft color haze sit behind the translucent dashboard.");
    }

    private void appearancePage(DrawContext c, Theme th, Config cfg, int y) {
        Theme[] all = Theme.values();
        int cols = 3, gap = 8, bw = (contentW - gap * (cols - 1)) / cols;
        for (int i = 0; i < all.length; i++) {
            int col = i % cols, row = i / cols;
            int bx = contentX + col * (bw + gap), by = y + row * 43;
            final int idx = i;
            boolean selected = cfg.theme == i;
            Draw.round(c, bx, by, bw, 35, 7, selected ? 0xAA4A5876 : 0xAA202B3D);
            Draw.round(c, bx + 8, by + 9, 16, 16, 8, all[i].accent);
            Draw.text(c, all[i].label, bx + 31, by + 13, selected ? th.text : th.sub);
            if (inside(bx, by, bw, 35) && justPressed) { cfg.theme = idx; Config.save(); }
        }
        card(c, contentX, y + 273, contentW, 48, th, "FROSTED GLASS", "Theme colors apply to the dashboard and the in-game HUD.");
    }

    private void audioPage(DrawContext c, Theme th, Config cfg, int y) {
        card(c, contentX, y, contentW, 77, th, "AUCTION FEEDBACK", "The bundled auction module plays bid and countdown sounds.");
        card(c, contentX, y + 89, contentW, 77, th, "PAYMENT ALERTS", "Incoming payments are recorded from server chat messages.");
        card(c, contentX, y + 178, contentW, 77, th, "SOUND CONTROL", "Use Minecraft's Music & Sounds settings to adjust auction audio.");
    }

    private void settingsPage(DrawContext c, Theme th, Config cfg, int y) {
        int half = (contentW - 12) / 2;
        card(c, contentX, y, contentW, 61, th, "BALANCE POLLING", "Checks /bal even while the HUD is hidden");
        button(c, "interval", contentX, y + 75, half, 30, "Every " + cfg.checkSeconds + " seconds", th, () -> {
            int idx = 0;
            for (int i = 0; i < Palette.INTERVALS.length; i++) if (Palette.INTERVALS[i] == cfg.checkSeconds) idx = i;
            cfg.checkSeconds = Palette.INTERVALS[(idx + 1) % Palette.INTERVALS.length]; Config.save();
        });
        button(c, "hide", contentX + half + 12, y + 75, half, 30, "Hide /bal reply: " + (cfg.hideReply ? "ON" : "OFF"), th,
                () -> { cfg.hideReply = !cfg.hideReply; Config.save(); });
        button(c, "track", contentX, y + 117, half, 30, "Tracker: " + (cfg.trackerEnabled ? "ON" : "OFF"), th,
                () -> { cfg.trackerEnabled = !cfg.trackerEnabled; Config.save(); });
        card(c, contentX, y + 164, contentW, 74, th, "COMMAND", "Type /opiod any time to open this dashboard.");
    }

    private void card(DrawContext c, int x, int y, int w, int h, Theme th, String title, String sub) {
        Draw.round(c, x, y, w, h, 9, 0xB51A2637);
        Draw.round(c, x, y, w, 2, 1, 0x887C91B5);
        Draw.text(c, title, x + 14, y + 11, th.sub);
        Draw.text(c, sub, x + 14, y + 32, th.text);
    }

    private void button(DrawContext c, String id, int x, int y, int w, int h, String label, Theme th, Runnable action) {
        boolean over = inside(x, y, w, h);
        Draw.round(c, x, y, w, h, 7, over ? 0xCC3B4C68 : 0xAA253247);
        Draw.round(c, x, y, 2, h, 1, th.accent);
        Draw.text(c, label, x + (w - Draw.width(label)) / 2, y + (h - 9) / 2, th.text);
        if (over && justPressed) action.run();
    }

    private boolean inside(int x, int y, int w, int h) {
        return mx >= x && mx < x + w && my >= y && my < y + h;
    }

    private static String iconFor(String name) {
        return switch (name) {
            case "Tracker" -> "◉";
            case "Auction" -> "◇";
            case "HUD" -> "▣";
            case "Visuals" -> "✧";
            case "Appearance" -> "◈";
            case "Audio" -> "♫";
            default -> "⚙";
        };
    }

    private static float ease(float t) { return 1f - (float)Math.pow(1f - Math.max(0f, Math.min(1f, t)), 3); }

    @Override public boolean shouldPause() { return false; }
}
''')



# The bundled auction classes must be on the compile classpath as well as inside the final JAR.
build_file = root / "build.gradle"
build_text = build_file.read_text()
if 'modCompileOnly files("libs/donut-auction-original.jar")' not in build_text:
    build_text = build_text.replace("dependencies {", 'dependencies {\n    compileOnly files("libs/donut-auction-original.jar")')
build_file.write_text(build_text)

# Accept the original auction module's optional-currency-symbol payment format.
ledger = src / "PaymentLedger.java"
ledger_text = ledger.read_text()
ledger_text = ledger_text.replace(
    'Pattern.compile("(?i)\\\\$\\\\s*([0-9][0-9,]*(?:\\\\.[0-9]+)?)\\\\s*([kmbt])?")',
    'Pattern.compile("(?i)\\\\$?\\\\s*([0-9][0-9,]*(?:\\\\.[0-9]+)?)\\\\s*([kmbt])?")'
)
ledger.write_text(ledger_text)

# Use Frosted Glass as the default preset for a closer match to the reference.
config = src / "Config.java"
config_text = config.read_text().replace("public int theme = 0;", "public int theme = 1;")
config.write_text(config_text)


# Keep the auction binary bundled and initialized, but use reflection from the UI.
# The supplied auction JAR is compiled in intermediary mappings, so direct Java imports
# cannot be compiled against it without a separate remapped API artifact.
build_file = root / "build.gradle"
build_text = build_file.read_text().replace('    modCompileOnly files("libs/donut-auction-original.jar")\n', "")
build_file.write_text(build_text)

screen = src / "SettingsScreen.java"
screen_text = screen.read_text()
screen_text = screen_text.replace("import com.donutauction.Auction;\n", "")
screen_text = screen_text.replace("import com.donutauction.AuctionScreen;\n", "")
screen_text = screen_text.replace("import com.donutauction.DonutAuctionClient;\n", "")
start = screen_text.index("    private void auctionPage(")
end = screen_text.index("    private void hudPage(", start)
screen_text = screen_text[:start] + r'''    private void auctionPage(DrawContext c, Theme th, int y) {
        card(c, contentX, y, contentW, 105, th, "STREAM AUCTION", "Every detected viewer payment can become a bid");
        boolean active = false;
        String itemName = "Waiting for auction";
        String topBid = "--";
        try {
            Class<?> clientClass = Class.forName("com.donutauction.DonutAuctionClient");
            Object auction = clientClass.getField("auction").get(null);
            if (auction != null) {
                Class<?> auctionClass = auction.getClass();
                active = auctionClass.getField("active").getBoolean(auction);
                Object item = auctionClass.getField("itemName").get(auction);
                Object bid = auctionClass.getField("highBid").get(auction);
                if (item != null) itemName = String.valueOf(item);
                if (bid instanceof Number n) topBid = MoneyFmt.compact(n.doubleValue());
            }
        } catch (Throwable ignored) {}
        Draw.text(c, active ? "Auction running" : "No active auction", contentX + 16, y + 47,
                active ? 0xFF5DE6A2 : th.sub);
        button(c, "openauction", contentX + contentW - 178, y + 38, 160, 28, "OPEN AUCTION", th, () -> {
            try {
                Class<?> screenClass = Class.forName("com.donutauction.AuctionScreen");
                Screen auctionScreen = (Screen) screenClass.getDeclaredConstructor().newInstance();
                MinecraftClient.getInstance().setScreen(auctionScreen);
            } catch (Throwable ignored) {
                MinecraftClient.getInstance().player.sendMessage(Text.literal("VØID: Auction module could not be opened."), false);
            }
        });
        card(c, contentX, y + 116, (contentW - 12) / 2, 74, th, "CURRENT ITEM", itemName);
        card(c, contentX + (contentW - 12) / 2 + 12, y + 116, (contentW - 12) / 2, 74, th, "TOP BID", topBid);
        card(c, contentX, y + 200, contentW, 68, th, "AUCTION MODULE", "Original Donut Auction module is loaded and initialized inside VØID.");
    }

''' + screen_text[end:]
screen.write_text(screen_text)


# Parse payment amounts after payment verbs so digits in usernames are never mistaken for money.
ledger = src / "PaymentLedger.java"
ledger_text = ledger.read_text()
ledger_text = ledger_text.replace(
    'private static final Pattern MONEY = Pattern.compile("(?i)\\\\$?\\\\s*([0-9][0-9,]*(?:\\\\.[0-9]+)?)\\\\s*([kmbt])?");',
    'private static final Pattern MONEY = Pattern.compile("(?i)\\\\$?\\\\s*([0-9][0-9,]*(?:\\\\.[0-9]+)?)\\\\s*([kmbt])?");\n    private static final Pattern PAYMENT_AMOUNT = Pattern.compile("(?i)(?:paid\\\\s+you|received|sent|transferred|purchased|payment(?:\\\\s+of)?)\\\\D{0,24}\\\\$?\\\\s*([0-9][0-9,]*(?:\\\\.[0-9]+)?)\\\\s*([kmbt])?");'
)
ledger_text = ledger_text.replace("Matcher m = MONEY.matcher(message);", "Matcher m = PAYMENT_AMOUNT.matcher(message);")
ledger_text = ledger_text.replace("if (overlay || message == null) return;", "if (overlay || message == null || !Config.get().trackerEnabled) return;")
ledger.write_text(ledger_text)


# Match the reference's 6-by-3 theme swatch grid and make frosted glass a real toggle.
screen = src / "SettingsScreen.java"
screen_text = screen.read_text()
screen_text = screen_text.replace("int cols = 3, gap = 8, bw = (contentW - gap * (cols - 1)) / cols;",
                                  "int cols = 6, gap = 7, bw = (contentW - gap * (cols - 1)) / cols;")
screen_text = screen_text.replace(
    'card(c, contentX, y + 273, contentW, 48, th, "FROSTED GLASS", "Theme colors apply to the dashboard and the in-game HUD.");',
    'button(c, "frosted", contentX, y + 145, contentW, 32, "Frosted glass: " + (cfg.glass ? "ON" : "OFF"), th, () -> { cfg.glass = !cfg.glass; Config.save(); });'
)
screen.write_text(screen_text)


# Migrate older VØID configs to the new five-second balance polling interval once.
config = src / "Config.java"
config_text = config.read_text()
config_text = config_text.replace("public int skyStyle = 0;", "public int skyStyle = 0;\n    public int configVersion = 0;")
config_text = config_text.replace(
    "if (checkSeconds < 5) checkSeconds = 5;",
    "if (configVersion < 2) { checkSeconds = 5; configVersion = 2; }\n        if (checkSeconds < 5) checkSeconds = 5;"
)
config.write_text(config_text)

# Combine rapid outgoing chat payments when reconciling them against the next /bal decrease.
ledger = src / "PaymentLedger.java"
ledger_text = ledger.read_text()
ledger_text = ledger_text.replace(
    "lastOutgoingAt = now;\n            lastOutgoingAmount = amount;",
    "if (now - lastOutgoingAt > 12000L) lastOutgoingAmount = 0d;\n            lastOutgoingAt = now;\n            lastOutgoingAmount += amount;"
)
ledger.write_text(ledger_text)


# Final release number for the payment-ledger and dashboard build.
meta = root / "src/main/resources/fabric.mod.json"
data = json.loads(meta.read_text())
data["version"] = "1.0.6"
meta.write_text(json.dumps(data, indent=2) + "\n")
props = root / "gradle.properties"
props_text = re.sub(r"(?m)^mod_version=.*$", "mod_version=1.0.6", props.read_text())
props.write_text(props_text)


# VØID 1.0.7: fast full-screen module transitions and a UI click sound.
screen = src / "SettingsScreen.java"
screen_text = screen.read_text()
if "import net.minecraft.client.sound.PositionedSoundInstance;" not in screen_text:
    screen_text = screen_text.replace(
        "import net.minecraft.client.gui.screen.Screen;\\n",
        "import net.minecraft.client.gui.screen.Screen;\\nimport net.minecraft.client.sound.PositionedSoundInstance;\\nimport net.minecraft.sound.SoundEvents;\\n"
    )
screen_text = screen_text.replace(
    '    private long transitionAt = 0L;\\n',
    '    private long transitionAt = 0L;\\n    private String queuedPage = null;\\n'
)
old_change = """    private void changePage(String next) {
        if (!page.equals(next)) {
            page = next;
            transitionAt = System.currentTimeMillis();
        }
    }"""
new_change = """    private void changePage(String next) {
        if (!page.equals(next) && queuedPage == null) {
            queuedPage = next;
            transitionAt = System.currentTimeMillis();
            MinecraftClient mc = MinecraftClient.getInstance();
            mc.getSoundManager().play(PositionedSoundInstance.master(SoundEvents.UI_BUTTON_CLICK, 0.85f));
        }
    }"""
screen_text = screen_text.replace(old_change, new_change)
old_render = """        float progress = transitionAt == 0L ? 1f : Math.min(1f, (System.currentTimeMillis() - transitionAt) / 230f);
        float slide = (1f - ease(progress)) * 18f;
        c.getMatrices().pushMatrix();
        c.getMatrices().translate(slide, 0f);
        renderPage(c, th, cfg);
        c.getMatrices().popMatrix();
        if (progress < 1f) {
            int a = (int)((1f - progress) * 70f);
            c.fill(contentX, top + 65, left + panelW - 10, top + panelH - 10, (a << 24));
        }"""
new_render = """        long elapsed = transitionAt == 0L ? 1000L : System.currentTimeMillis() - transitionAt;
        if (queuedPage != null && elapsed >= 72L) {
            page = queuedPage;
            queuedPage = null;
        }
        renderPage(c, th, cfg);
        if (transitionAt != 0L && elapsed < 180L) {
            // 72ms fade to black, swap module at full black, then fade back in.
            float alpha = elapsed < 72L ? elapsed / 72f : 1f - ((elapsed - 72L) / 108f);
            alpha = Math.max(0f, Math.min(1f, alpha));
            c.fill(0, 0, width, height, ((int)(alpha * 245f) << 24));
        } else if (transitionAt != 0L) {
            transitionAt = 0L;
        }"""
if old_render not in screen_text:
    raise RuntimeError("Could not find expected VØID page-transition render block")
screen_text = screen_text.replace(old_render, new_render)
screen.write_text(screen_text)

# Bump the packaged release to 1.0.7.
meta = root / "src/main/resources/fabric.mod.json"
data = json.loads(meta.read_text())
data["version"] = "1.0.7"
meta.write_text(json.dumps(data, indent=2) + "\\n")
props = root / "gradle.properties"
props_text = re.sub(r"(?m)^mod_version=.*$", "mod_version=1.0.7", props.read_text())
props.write_text(props_text)


# Repair 1.0.7 transition patch: ensure field/imports exist and metadata is valid JSON.
screen = src / "SettingsScreen.java"
screen_text = screen.read_text()
if "import net.minecraft.client.sound.PositionedSoundInstance;" not in screen_text:
    screen_text = screen_text.replace(
        "import net.minecraft.client.gui.screen.Screen;",
        "import net.minecraft.client.gui.screen.Screen;" + chr(10) +
        "import net.minecraft.client.sound.PositionedSoundInstance;" + chr(10) +
        "import net.minecraft.sound.SoundEvents;"
    )
if "private String queuedPage = null;" not in screen_text:
    screen_text = screen_text.replace(
        "private long transitionAt = 0L;",
        "private long transitionAt = 0L;" + chr(10) + "    private String queuedPage = null;"
    )
screen.write_text(screen_text)

meta = root / "src/main/resources/fabric.mod.json"
meta_text = meta.read_text().removesuffix(chr(92) + "n").rstrip()
meta.write_text(meta_text + chr(10))
json.loads(meta.read_text())


# VØID 1.0.8: X opens the dashboard, join chime, and panel-only transitions.
screen = src / "SettingsScreen.java"
screen_text = screen.read_text()
# Restrict the transition overlay to the dashboard surface; never cover the game world.
screen_text = screen_text.replace(
    "c.fill(0, 0, width, height, ((int)(alpha * 245f) << 24));",
    "c.fill(left + 1, top + 1, left + panelW - 1, top + panelH - 1, ((int)(alpha * 245f) << 24));"
)
# Clean up the transition by keeping its fade inside the rounded dashboard bounds.
screen_text = screen_text.replace(
    "c.fill(0, 0, width, height,",
    "c.fill(left + 1, top + 1, left + panelW - 1, top + panelH - 1,"
)
screen.write_text(screen_text)

client = src / "NineStyleClient.java"
client_text = client.read_text()
imports = [
    "import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;",
    "import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;",
    "import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;",
    "import net.minecraft.client.option.KeyBinding;",
    "import net.minecraft.client.util.InputUtil;",
    "import net.minecraft.client.sound.PositionedSoundInstance;",
    "import net.minecraft.sound.SoundEvents;",
    "import org.lwjgl.glfw.GLFW;"
]
for imp in imports:
    if imp not in client_text:
        client_text = client_text.replace("package com.ninestyle;", "package com.ninestyle;\\n" + imp, 1)
needle = "public void onInitializeClient() {"
if needle not in client_text:
    needle = "public void onInitializeClient()"
    if needle not in client_text:
        raise RuntimeError("Could not locate client initializer for X keybind")
    brace = client_text.index("{", client_text.index(needle)) + 1
else:
    brace = client_text.index(needle) + len(needle)
setup = r"""
        KeyBinding voidOpenKey = KeyBindingHelper.registerKeyBinding(
            new KeyBinding("key.void.open_menu", InputUtil.Type.KEYSYM, GLFW.GLFW_KEY_X,
                KeyBinding.Category.MISC)
        );
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            while (voidOpenKey.wasPressed()) {
                if (client.currentScreen == null) client.setScreen(new SettingsScreen());
            }
        });
        ClientPlayConnectionEvents.JOIN.register((handler, sender, client) ->
            client.execute(() -> client.getSoundManager().play(
                PositionedSoundInstance.master(SoundEvents.UI_TOAST_IN, 0.8f)
            ))
        );
"""
client_text = client_text[:brace] + setup + client_text[brace:]
client.write_text(client_text)

# Keep release metadata and Gradle artifact version synchronized.
import json, re
meta = root / "src/main/resources/fabric.mod.json"
data = json.loads(meta.read_text())
data["version"] = "1.0.8"
data["name"] = "VØID Streamer Essentials"
meta.write_text(json.dumps(data, indent=2) + chr(10))
props = root / "gradle.properties"
props.write_text(re.sub(r"(?m)^mod_version=.*$", "mod_version=1.0.8", props.read_text()))


# Repair escaped newline sequences introduced by the X-key patch before compilation.
client = src / "NineStyleClient.java"
client_text = client.read_text()
client_text = client_text.replace(chr(92) + "n", chr(10))
client.write_text(client_text)


# VØID 1.0.9: make the auction controls a native page inside the VØID dashboard.
screen = src / "SettingsScreen.java"
screen_text = screen.read_text()
if "private int auctionDurationChoice" not in screen_text:
    screen_text = screen_text.replace(
        "private String page = \"Overview\";",
        "private String page = \"Overview\";" + chr(10) +
        "    private int auctionDurationChoice = 1;" + chr(10) +
        "    private int auctionBidChoice = 1;"
    )

start = screen_text.index("    private void auctionPage(")
end = screen_text.index("    private void hudPage(", start)
auction_method = r'''    private void auctionPage(DrawContext c, Theme th, int y) {
        int gap = 10;
        int half = (contentW - gap) / 2;
        boolean active = false;
        String itemName = "No active auction";
        String leader = "—";
        String topBid = "$0";
        String timeLeft = "Ready";
        try {
            Class<?> clientClass = Class.forName("com.donutauction.DonutAuctionClient");
            Object auction = clientClass.getField("auction").get(null);
            if (auction != null) {
                Class<?> ac = auction.getClass();
                active = ac.getField("active").getBoolean(auction);
                Object item = ac.getField("itemName").get(auction);
                Object who = ac.getField("leader").get(auction);
                if (item != null) itemName = String.valueOf(item);
                if (who != null && !String.valueOf(who).isBlank()) leader = String.valueOf(who);
                topBid = MoneyFmt.compact(ac.getField("highBid").getDouble(auction));
                long remaining = Math.max(0L, ac.getField("endAt").getLong(auction) - System.currentTimeMillis());
                timeLeft = String.format("%d:%02d", remaining / 60000L, (remaining / 1000L) % 60L);
            }
        } catch (Throwable ignored) {}

        Draw.round(c, contentX, y, contentW, 76, 10, 0xC51A2637);
        Draw.round(c, contentX, y, 3, 76, 2, active ? 0xFF5DE6A2 : th.accent);
        Draw.text(c, "LIVE AUCTION", contentX + 16, y + 12, th.sub);
        Draw.text(c, itemName, contentX + 16, y + 32, th.text);
        Draw.text(c, active ? "RUNNING" : "READY", contentX + contentW - 92, y + 15,
                active ? 0xFF5DE6A2 : th.sub);

        card(c, contentX, y + 88, half, 62, th, "TOP BID", topBid);
        card(c, contentX + half + gap, y + 88, half, 62, th, "TIME LEFT", timeLeft);
        card(c, contentX, y + 160, half, 62, th, "HIGH BIDDER", leader);
        card(c, contentX + half + gap, y + 160, half, 62, th, "BID EXTENSION",
                "3 sec: " + extensionEnabled());

        String[] durations = {"30 seconds", "1 minute", "2 minutes", "5 minutes"};
        long[] durationMs = {30000L, 60000L, 120000L, 300000L};
        double[] bids = {1d, 10d, 100d, 1000d};
        String[] bidLabels = {"$1", "$10", "$100", "$1,000"};
        button(c, "auctionduration", contentX, y + 235, half, 30,
                "Duration: " + durations[auctionDurationChoice], th,
                () -> auctionDurationChoice = (auctionDurationChoice + 1) % durations.length);
        button(c, "auctionminbid", contentX + half + gap, y + 235, half, 30,
                "Minimum bid: " + bidLabels[auctionBidChoice], th,
                () -> auctionBidChoice = (auctionBidChoice + 1) % bids.length);

        if (active) {
            button(c, "auctionstop", contentX, y + 276, contentW, 32,
                    "END AUCTION", th, () -> {
                        try {
                            Class.forName("com.donutauction.DonutAuctionClient")
                                .getMethod("cancel").invoke(null);
                        } catch (Throwable ex) {
                            MinecraftClient.getInstance().player.sendMessage(
                                Text.literal("VØID: Could not end the auction."), false);
                        }
                    });
        } else {
            button(c, "auctionstart", contentX, y + 276, contentW, 32,
                    "START AUCTION WITH HELD ITEM", th, () -> {
                        try {
                            MinecraftClient mc = MinecraftClient.getInstance();
                            if (mc.player == null) return;
                            Object stack = mc.player.getMainHandStack();
                            if (stack == null || (Boolean) stack.getClass().getMethod("isEmpty").invoke(stack)) {
                                mc.player.sendMessage(Text.literal("VØID: Hold the item you want to auction."), false);
                                return;
                            }
                            String name = String.valueOf(stack.getClass().getMethod("getName").invoke(stack)
                                .getClass().getMethod("getString").invoke(
                                    stack.getClass().getMethod("getName").invoke(stack)));
                            int count = ((Number) stack.getClass().getMethod("getCount").invoke(stack)).intValue();
                            Class<?> dc = Class.forName("com.donutauction.DonutAuctionClient");
                            dc.getMethod("startAuction", stack.getClass(), String.class, long.class,
                                double.class, double.class, int.class)
                                .invoke(null, stack, name, durationMs[auctionDurationChoice],
                                    bids[auctionBidChoice], 0d, count);
                        } catch (Throwable ex) {
                            MinecraftClient.getInstance().player.sendMessage(
                                Text.literal("VØID: Auction could not be started. Check the item in your hand."), false);
                        }
                    });
        }
        button(c, "auctionextension", contentX, y + 317, contentW, 28,
                "Toggle 3-second bid extension", th, () -> {
                    try {
                        Class.forName("com.donutauction.DonutAuctionClient")
                            .getMethod("toggleBidTimeExtension").invoke(null);
                    } catch (Throwable ignored) {}
                });
        Draw.text(c, "Choose an item in your hand, set the duration and minimum bid, then start.",
            contentX + 2, y + 354, th.sub);
    }

    private boolean extensionEnabled() {
        try {
            return Class.forName("com.donutauction.DonutAuctionClient")
                .getField("addThreeSecondsPerBid").getBoolean(null);
        } catch (Throwable ignored) { return false; }
    }

'''
screen_text = screen_text[:start] + auction_method + screen_text[end:]
screen.write_text(screen_text)

# Release metadata for the integrated auction dashboard.
meta = root / "src/main/resources/fabric.mod.json"
data = json.loads(meta.read_text())
data["version"] = "1.0.9"
meta.write_text(json.dumps(data, indent=2) + chr(10))
props = root / "gradle.properties"
props.write_text(re.sub(r"(?m)^mod_version=.*$", "mod_version=1.0.9", props.read_text()))
