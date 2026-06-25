"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, fetcher } from "@/lib/api";
import { setToken } from "@/lib/auth";

type LoginResponse = { access_token: string; token_type: string };
type BootstrapStatus = { needs_admin: boolean };

function formatError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String((err as { message?: string }).message ?? "Failed");
}

export default function LoginPage() {
  const router = useRouter();
  // Unauthed call — flips to false the instant the first user registers.
  const { data: status, mutate: refetchStatus } = useSWR<BootstrapStatus>(
    "/auth/bootstrap-needed",
    fetcher,
    { revalidateOnFocus: false },
  );

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const isBootstrap = status?.needs_admin === true;

  async function login(emailValue: string, passwordValue: string): Promise<void> {
    const form = new URLSearchParams({ username: emailValue, password: passwordValue });
    const resp = await api<LoginResponse>("/auth/jwt/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
    setToken(resp.access_token);
    router.push("/dashboard");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isBootstrap) {
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        await refetchStatus();
      }
      await login(email, password);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  const title = isBootstrap ? "Create admin account" : "Maelstrom";
  const cta = isBootstrap ? "Create admin" : "Sign in";
  const ctaBusy = isBootstrap ? "Creating…" : "Signing in…";

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-center">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          {isBootstrap && (
            <p className="mb-4 text-xs text-muted-foreground">
              No users exist yet — this first account becomes the admin. Use a strong password and
              keep these credentials safe.
            </p>
          )}
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete={isBootstrap ? "new-password" : "current-password"}
                minLength={isBootstrap ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? ctaBusy : cta}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
