import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const mediaRoot = path.resolve(__dirname, "src/imageFile");

const contentTypes = {
  ".gif": "image/gif",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".tif": "image/tiff",
  ".tiff": "image/tiff",
  ".webp": "image/webp",
  ".zip": "application/zip",
};

function devMediaFilePlugin() {
  return {
    name: "dev-media-file-server",
    configureServer(server) {
      server.middlewares.use("/imageFile", (req, res, next) => {
        const urlPath = decodeURIComponent((req.url || "").split("?")[0]);
        const filePath = path.resolve(mediaRoot, `.${urlPath}`);
        const mediaRootPrefix = `${mediaRoot}${path.sep}`.toLowerCase();
        const normalizedFilePath = filePath.toLowerCase();

        if (
          normalizedFilePath !== mediaRoot.toLowerCase() &&
          !normalizedFilePath.startsWith(mediaRootPrefix)
        ) {
          res.statusCode = 403;
          res.end("Forbidden");
          return;
        }

        fs.stat(filePath, (statError, stat) => {
          if (statError || !stat.isFile()) {
            next();
            return;
          }

          res.statusCode = 200;
          res.setHeader("Content-Length", stat.size);
          res.setHeader(
            "Content-Type",
            contentTypes[path.extname(filePath).toLowerCase()] ||
              "application/octet-stream",
          );
          fs.createReadStream(filePath).pipe(res);
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [devMediaFilePlugin(), react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8001",
      "/imageFile": "http://127.0.0.1:8001",
    },
  },
});
