import path from "path";
import commonjs from "@rollup/plugin-commonjs";
import { nodeResolve } from "@rollup/plugin-node-resolve";
import replace from "@rollup/plugin-replace";
import typescript from "@rollup/plugin-typescript";

const deckyShimPlugin = {
  name: "decky-ui-shim",
  resolveId(source) {
    if (source === "@decky/ui") {
      return path.resolve("preview/deckyUiShim.tsx");
    }
    return null;
  },
};

export default {
  input: "preview/harness.tsx",
  output: {
    file: "preview/preview_bundle.js",
    format: "iife",
    name: "SwitchDeckPreview",
    sourcemap: false,
  },
  plugins: [
    deckyShimPlugin,
    replace({
      preventAssignment: true,
      "process.env.NODE_ENV": JSON.stringify("production"),
    }),
    nodeResolve({
      browser: true,
      extensions: [".js", ".jsx", ".ts", ".tsx"],
    }),
    commonjs(),
    typescript({
      tsconfig: false,
      compilerOptions: {
        target: "ES2020",
        module: "ESNext",
        jsx: "react-jsx",
        strict: true,
        moduleResolution: "bundler",
        esModuleInterop: true,
        allowSyntheticDefaultImports: true,
        skipLibCheck: true,
      },
      include: ["preview/**/*.ts", "preview/**/*.tsx", "src/ui/**/*.ts", "src/ui/**/*.tsx"],
    }),
  ],
};
