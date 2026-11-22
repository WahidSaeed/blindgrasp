import { Config } from "@remotion/cli/config";
// Remotion's downloaded headless shell is missing its ICU data here; use the installed Chrome.
Config.setBrowserExecutable("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
Config.setChromeMode("chrome-for-testing");
