export type Version = [number, number, number];

export const formatPackageVersion = (version: string | undefined | null) =>
  version?.replace(/\+b([1-9][0-9]*)$/, ' — Build $1');

export const parsePackageVersion = (version: string | undefined | null) => {
  const match = version?.match(
    /^v?([0-9]+)\.([0-9]+)\.([0-9]+)(?:-asus[0-9]+)?(?:\+b([0-9]+))?$/,
  );
  return {
    version: (match
      ? [Number(match[1]), Number(match[2]), Number(match[3])]
      : [0, 0, 0]) as Version,
    packageVersion: version || undefined,
    buildNumber: match?.[4],
  };
};

export function compareVersions(current: Version, latest: Version) {
  const v1 = latest[0] - current[0];
  const v2 = latest[1] - current[1];
  const v3 = latest[2] - current[2];
  if (v1) return v1 > 0;
  if (v2) return v2 > 0;
  if (v3) return v3 > 0;
  return false;
}
