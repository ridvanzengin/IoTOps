import type { SVGProps } from "react";

function Icon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    />
  );
}

export function HomeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5 10v10h14V10" />
    </Icon>
  );
}

export function CollectorIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M12 3 3 7.5 12 12l9-4.5L12 3Z" />
      <path d="M3 12l9 4.5 9-4.5" />
      <path d="M3 16.5 12 21l9-4.5" />
    </Icon>
  );
}

export function AutomaterIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
    </Icon>
  );
}

export function VisualizerIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <line x1="4" y1="20" x2="4" y2="11" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="20" y1="20" x2="20" y2="15" />
    </Icon>
  );
}

export function ProjectIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
    </Icon>
  );
}

export function MoreIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props} strokeWidth="0" fill="currentColor">
      <circle cx="12" cy="5" r="1.6" />
      <circle cx="12" cy="12" r="1.6" />
      <circle cx="12" cy="19" r="1.6" />
    </Icon>
  );
}

export function PlusIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </Icon>
  );
}

export function CopilotIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props} strokeWidth="0" fill="currentColor">
      <path d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
    </Icon>
  );
}
