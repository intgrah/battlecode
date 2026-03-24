import { readFile } from "fs/promises";
import { resolve } from "path";
import { env } from "$env/dynamic/private";

export async function GET({ url }) {
  const file =
    url.searchParams.get("file") || env.REPLAY_FILE || "replay.replay26";
  const replayPath = resolve(process.cwd(), "..", file);

  const data = await readFile(replayPath);
  return new Response(data, {
    headers: { "Content-Type": "application/octet-stream" },
  });
}
