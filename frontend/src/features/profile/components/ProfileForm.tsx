"use client";

import { ChevronDown } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, type ReactNode, useState } from "react";
import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { safeNextPath } from "@/features/auth/lib";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Field, fieldA11y } from "@/components/ui/Field";
import { TextField } from "@/components/ui/TextField";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { ApiError, getMyProfile, saveMyProfile } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/useApi";
import {
  BUSAN_SIDO,
  BUSAN_SIGUNGU_OPTIONS,
  EDUCATION_OPTIONS,
  EMPLOYMENT_OPTIONS,
  GRADUATE_SCHOOL,
  GRADUATION_OPTIONS,
  HIGHER_EDUCATION,
  JOB_FIELD_OPTIONS,
  MAX_PRIORITIES,
  PRIORITY_OPTIONS,
  SIDO_OPTIONS,
} from "../options";
import type { BasicProfile, BasicProfileInput } from "../types";
import { CertificateInput } from "./CertificateInput";

type Option = { value: string; label: string };

function Select({
  id,
  label,
  value,
  onChange,
  options,
  placeholder,
  error,
  required = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<Option>;
  placeholder: string;
  error?: string;
  /** 꼭 골라야 하는 칸이면 펼친 목록에서 안내 문구를 고를 수 없게 한다 */
  required?: boolean;
}) {
  return (
    <Field id={id} label={label} error={error}>
      {/* 브라우저 기본 화살표를 지우고 TextField와 같은 여백·화살표 아이콘을 쓴다. 펼친 목록은 기기 기본 목록 그대로다 */}
      <div className="relative w-full">
        <select
          {...fieldA11y(id, error)}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={cn(
            "h-12 w-full cursor-pointer appearance-none rounded-field border bg-white pr-11 pl-3.75 text-body transition-colors hover:border-grey-400 focus:border-blue-500 focus:outline-none",
            value ? "text-grey-900" : "text-grey-500",
            error ? "border-red-500 hover:border-red-500" : "border-grey-300",
          )}
        >
          <option value="" disabled={required} className="text-grey-500">
            {placeholder}
          </option>
          {options.map((option) => (
            <option key={option.value} value={option.value} className="text-grey-900">
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden
          className="pointer-events-none absolute top-1/2 right-3.75 size-5 -translate-y-1/2 text-grey-500"
          strokeWidth={2}
        />
      </div>
    </Field>
  );
}

function Row({ children }: { children: ReactNode }) {
  // 두 칸 격자: 칸이 하나뿐이어도(부산이 아닌 지역) 반 폭을 지켜 구·군이 나타날 때 왼쪽 칸이 줄어들지 않는다
  return <div className="grid w-full gap-5 sm:grid-cols-2">{children}</div>;
}

/** 만 15~75세가 고를 수 있는 출생 연도. 백엔드는 1950~2015를 받는다. */
const BIRTH_YEARS: Option[] = Array.from({ length: 2011 - 1950 + 1 }, (_, i) => {
  const year = String(2011 - i);
  return { value: year, label: `${year}년` };
});

type FormState = {
  birthYear: string;
  residenceSido: string;
  residenceSigungu: string;
  educationLevel: string;
  graduationStatus: string;
  schoolRegion: string;
  schoolName: string;
  employmentStatus: string;
  major: string;
  certificates: string[];
  jobField: string;
  jobName: string;
  priorities: string[];
};

const FIELD_VALUES: ReadonlySet<string> = new Set(JOB_FIELD_OPTIONS.map((option) => option.value));

/** 저장된 프로필로 입력칸을 채운다. 희망 직무는 분야 이름과 직무 이름으로 나눠 읽는다. */
function toForm(profile: BasicProfile | null): FormState {
  const jobs = profile?.desiredJobs ?? [];
  return {
    birthYear: profile?.birthYear ? String(profile.birthYear) : "",
    residenceSido: profile?.residenceSido ?? "",
    residenceSigungu: profile?.residenceSigungu ?? "",
    educationLevel: profile?.educationLevel ?? "",
    graduationStatus: profile?.graduationStatus ?? "",
    schoolRegion: profile?.universityRegion ?? "",
    schoolName: profile?.schoolName ?? "",
    employmentStatus: profile?.employmentStatus ?? "",
    major: profile?.major ?? "",
    certificates: profile?.certificates ?? [],
    jobField: jobs.find((job) => FIELD_VALUES.has(job.name))?.name ?? "",
    jobName: jobs.find((job) => !FIELD_VALUES.has(job.name))?.name ?? "",
    priorities: profile?.priorities ?? [],
  };
}

/**
 * 기본 프로필 입력 (`PUT /api/v1/me/profile`). 공고 추천과 정책 자격 판정에 쓰는 값만 받는다.
 * 소셜 로그인으로 처음 들어오면 이 화면을 먼저 거친다.
 */
export function ProfileForm() {
  const [loaded, reload] = useApi("me-profile", getMyProfile);

  if (loaded.status === "loading") return <PageSkeleton label="프로필을 불러오는 중" sections={2} />;
  if (loaded.status === "error") return <ApiErrorNotice error={loaded.error} onRetry={reload} />;
  return <ProfileFields profile={loaded.data} />;
}

function ProfileFields({ profile }: { profile: BasicProfile | null }) {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const [form, setForm] = useState<FormState>(() => toForm(profile));
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [failure, setFailure] = useState<string>();
  const [pending, setPending] = useState(false);

  // 값을 고치면 그 칸의 오류 문구는 바로 지운다
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev));
  };
  const inBusan = form.residenceSido === BUSAN_SIDO;
  const higherEducation = HIGHER_EDUCATION.has(form.educationLevel);
  const highSchool = form.educationLevel === "HIGH_SCHOOL";

  // 고른 순서를 지킨다. 서버는 3개까지만 받는다
  function togglePriority(value: string) {
    setForm((prev) => {
      if (prev.priorities.includes(value)) return { ...prev, priorities: prev.priorities.filter((p) => p !== value) };
      if (prev.priorities.length >= MAX_PRIORITIES) return prev;
      return { ...prev, priorities: [...prev.priorities, value] };
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found: Partial<Record<keyof FormState, string>> = {};
    if (!form.birthYear) found.birthYear = "출생 연도를 골라 주세요.";
    if (!form.residenceSido) found.residenceSido = "사는 지역을 골라 주세요.";
    if (inBusan && !form.residenceSigungu) found.residenceSigungu = "구·군을 골라 주세요.";
    if (!form.educationLevel) found.educationLevel = "최종 학력을 골라 주세요.";
    if (!form.employmentStatus) found.employmentStatus = "지금 상태를 골라 주세요.";
    if (!form.jobField) found.jobField = "희망 분야를 골라 주세요.";
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const jobName = form.jobName.trim();
    const major = form.major.trim();
    const schoolName = form.schoolName.trim();
    // 직무 이름을 적었으면 앞에 둔다. 분야 이름은 공공기관 공고의 분류와 맞추는 데 쓴다.
    // 이름이 그대로인 직무는 저장돼 있던 직무 코드(NCS 등)를 지우지 않고 함께 보낸다
    const keep = (name: string) => profile?.desiredJobs?.find((job) => job.name === name) ?? { name };
    const desiredJobs = [...(jobName ? [keep(jobName)] : []), keep(form.jobField)];
    const body: BasicProfileInput = {
      birthYear: Number(form.birthYear),
      residenceSido: form.residenceSido,
      residenceSigungu: inBusan ? form.residenceSigungu : null,
      educationLevel: form.educationLevel,
      graduationStatus: form.graduationStatus || null,
      // 학교 지역은 학력을 고른 경우에만, 대학 이름은 전문대 이상일 때만 보낸다 (고졸로 바꾸면 이름을 지운다)
      universityRegion: (higherEducation || highSchool) && form.schoolRegion ? form.schoolRegion : null,
      schoolName: higherEducation && schoolName ? schoolName : null,
      employmentStatus: form.employmentStatus,
      major: major || null,
      certificates: form.certificates.length > 0 ? form.certificates : null,
      desiredJobs,
      desiredRegion: "ALL",
      priorities: form.priorities,
    };

    setPending(true);
    setFailure(undefined);
    try {
      await saveMyProfile(body);
      router.replace(next);
    } catch (e) {
      setFailure(e instanceof ApiError && e.status === 400 ? e.message : "저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.");
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex w-full flex-col gap-5">
      <Row>
        <Select
          id="profile-birth-year"
          label="출생 연도"
          value={form.birthYear}
          onChange={(value) => set("birthYear", value)}
          options={BIRTH_YEARS}
          placeholder="선택"
          required
          error={errors.birthYear}
        />
        <Select
          id="profile-employment"
          label="지금 상태"
          value={form.employmentStatus}
          onChange={(value) => set("employmentStatus", value)}
          options={EMPLOYMENT_OPTIONS}
          placeholder="선택"
          required
          error={errors.employmentStatus}
        />
      </Row>
      <Row>
        <Select
          id="profile-sido"
          label="사는 지역"
          value={form.residenceSido}
          onChange={(value) => {
            setForm((prev) => ({ ...prev, residenceSido: value, residenceSigungu: "" }));
            setErrors((prev) => ({ ...prev, residenceSido: undefined, residenceSigungu: undefined }));
          }}
          options={SIDO_OPTIONS}
          placeholder="선택"
          required
          error={errors.residenceSido}
        />
        {inBusan && (
          <Select
            id="profile-sigungu"
            label="구·군"
            value={form.residenceSigungu}
            onChange={(value) => set("residenceSigungu", value)}
            options={BUSAN_SIGUNGU_OPTIONS}
            placeholder="선택"
            required
            error={errors.residenceSigungu}
          />
        )}
      </Row>
      <Row>
        <Select
          id="profile-education"
          label="최종 학력"
          value={form.educationLevel}
          onChange={(value) => set("educationLevel", value)}
          options={EDUCATION_OPTIONS}
          placeholder="선택"
          required
          error={errors.educationLevel}
        />
        <Select
          id="profile-graduation"
          label="졸업 상태 (선택)"
          value={form.graduationStatus}
          onChange={(value) => set("graduationStatus", value)}
          options={GRADUATION_OPTIONS}
          placeholder="선택 안 함"
        />
      </Row>
      {(higherEducation || highSchool) && (
        <div className="flex w-full flex-col gap-2.5">
          <Row>
            {higherEducation && (
              <TextField
                id="profile-school-name"
                label={GRADUATE_SCHOOL.has(form.educationLevel) ? "학부 대학 이름 (선택)" : "학교 이름 (선택)"}
                placeholder="예: 부산대학교"
                maxLength={50}
                value={form.schoolName}
                onChange={(event) => set("schoolName", event.target.value)}
              />
            )}
            <Select
              id="profile-school-region"
              label={highSchool ? "고등학교 지역 (선택)" : "학교 지역 (선택)"}
              value={form.schoolRegion}
              onChange={(value) => set("schoolRegion", value)}
              options={SIDO_OPTIONS}
              placeholder="선택 안 함"
            />
          </Row>
          <p className="text-small text-grey-600">
            학교 지역으로 비수도권·이전지역 인재 같은 지역 혜택 대상인지 함께 살펴 알려 드려요.
            {GRADUATE_SCHOOL.has(form.educationLevel) && " 대학원을 마쳤다면 학부 대학 기준이에요."}
          </p>
        </div>
      )}
      <TextField
        id="profile-major"
        label="전공 (선택)"
        placeholder="예: 통계학"
        maxLength={50}
        value={form.major}
        onChange={(event) => set("major", event.target.value)}
      />
      <CertificateInput id="profile-certificates" value={form.certificates} onChange={(next) => set("certificates", next)} />
      <Row>
        <Select
          id="profile-job-field"
          label="희망 분야"
          value={form.jobField}
          onChange={(value) => set("jobField", value)}
          options={JOB_FIELD_OPTIONS}
          placeholder="선택"
          required
          error={errors.jobField}
        />
        <TextField
          id="profile-job-name"
          label="희망 직무 (선택)"
          placeholder="예: 데이터 분석"
          maxLength={50}
          value={form.jobName}
          onChange={(event) => set("jobName", event.target.value)}
        />
      </Row>
      <fieldset className="flex w-full flex-col gap-2">
        <legend className="mb-2 text-small font-medium text-grey-700">중요하게 보는 것 (선택, {MAX_PRIORITIES}개까지)</legend>
        <div className="flex flex-wrap gap-2">
          {PRIORITY_OPTIONS.map((option) => (
            <Chip key={option.value} selected={form.priorities.includes(option.value)} onClick={() => togglePriority(option.value)}>
              {option.label}
            </Chip>
          ))}
        </div>
      </fieldset>
      {failure && (
        <p role="alert" className="text-small text-red-500">
          {failure}
        </p>
      )}
      <Button type="submit" fullWidth disabled={pending}>
        {pending ? "저장 중" : "저장하고 시작하기"}
      </Button>
    </form>
  );
}
