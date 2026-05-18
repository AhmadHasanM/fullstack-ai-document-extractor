"use client";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
};

export default function Button({
  children,
  loading,
  className = "",
  ...props
}: Props) {
  return (
    <button
      {...props}
      className={`px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 ${className}`}
    >
      {loading ? "Loading..." : children}
    </button>
  );
}