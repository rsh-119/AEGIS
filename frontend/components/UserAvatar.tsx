import clsx from "clsx";
import { avatarColor } from "./StockLogo";

/** A user's profile photo, or — same fallback precedent as StockLogo's
 * ticker-initials avatar — a colored circle of their username's first two
 * letters, hashed to one of the same fixed palette so it stays consistent
 * across renders/sessions without storing a color anywhere. */
export function UserAvatar({
  avatarUrl,
  username,
  sizeClass = "h-10 w-10",
  textClass = "text-sm",
  className,
}: {
  avatarUrl?: string | null;
  username: string;
  sizeClass?: string;
  textClass?: string;
  className?: string;
}) {
  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={`${username}'s profile photo`}
        className={clsx(sizeClass, "shrink-0 rounded-full object-cover", className)}
      />
    );
  }
  return (
    <div
      className={clsx(
        "flex shrink-0 items-center justify-center rounded-full font-bold text-white",
        sizeClass, textClass, avatarColor(username), className,
      )}
      role="img"
      aria-label={`${username}'s profile photo`}
    >
      {username.slice(0, 2).toUpperCase()}
    </div>
  );
}
