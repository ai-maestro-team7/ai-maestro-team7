"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import { ApiError, login } from "@/lib/api";
import { readDevModeFlag } from "../devMode";
import { safeNextPath } from "../lib";

/** 아이디·비밀번호 로그인 (`POST /api/v1/auth/login`). 회원가입은 없고 관리자가 만든 계정만 쓴다. */
export function LoginForm() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("아이디와 비밀번호를 입력해 주세요.");
      return;
    }
    setPending(true);
    setError(undefined);
    try {
      await login(username.trim(), password, readDevModeFlag());
      router.replace(next);
    } catch (e) {
      // 아이디가 없든 비밀번호가 틀리든 같은 문구 (docs/api.md §3)
      setError(
        e instanceof ApiError && e.status === 401
          ? "아이디 또는 비밀번호가 맞지 않아요."
          : "로그인하지 못했어요. 잠시 뒤 다시 시도해 주세요.",
      );
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex w-full flex-col gap-4">
      <TextField
        id="login-username"
        label="아이디"
        autoComplete="username"
        value={username}
        onChange={(event) => setUsername(event.target.value)}
      />
      <TextField
        id="login-password"
        label="비밀번호"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={error}
      />
      <Button type="submit" fullWidth disabled={pending}>
        {pending ? "로그인 중" : "로그인"}
      </Button>
    </form>
  );
}
