"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Mouse } from "@/components/ui/Mouse";
import { Button } from "@/components/ui/Button";

export default function LoginPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/documents/stats", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setError("Wrong access code. Try again.");
        setLoading(false);
        return;
      }
      // Valid — persist token in a cookie (30 days).
      document.cookie = `documouse_token=${encodeURIComponent(token)}; path=/; max-age=${30 * 86400}; SameSite=Lax`;
      router.replace("/");
    } catch {
      setError("Can't reach the server. Is the backend running?");
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm animate-rise space-y-6 rounded-xl border border-line bg-surface p-8 shadow-2"
      >
        <div className="flex flex-col items-center gap-2">
          <Mouse className="size-10" />
          <h1 className="font-display text-2xl">DocuMouse</h1>
          <p className="text-center text-sm text-ink-3">
            Enter your access code to continue.
          </p>
        </div>

        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Access code"
          autoFocus
          required
          className="h-11 w-full rounded-lg border border-line-strong bg-paper px-4 text-[15px] placeholder:text-ink-4 focus:border-focus focus:outline-none focus:ring-2 focus:ring-focus/20"
        />

        {error && (
          <p className="rounded-lg bg-danger-soft px-3 py-2 text-[13.5px] text-danger">
            {error}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          size="lg"
          className="w-full"
          disabled={loading || !token}
        >
          {loading ? "Checking…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
