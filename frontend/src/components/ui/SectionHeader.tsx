import { ArrowLink } from "./ArrowLink";

type SectionHeaderProps = {
  id?: string;
  title: string;
  href?: string;
  linkLabel?: string;
};

/** 영역 제목 (H2 19px) + 오른쪽 "전체 보기" 링크. */
export function SectionHeader({ id, title, href, linkLabel = "전체 보기" }: SectionHeaderProps) {
  return (
    <div className="flex w-full items-center justify-between">
      <h2 id={id} className="text-h2 font-bold text-grey-900">
        {title}
      </h2>
      {href && <ArrowLink href={href}>{linkLabel}</ArrowLink>}
    </div>
  );
}
