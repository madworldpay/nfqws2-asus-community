import { API } from '@/api/client';
import type { FilenamesRequest } from '@/api/schema';

export const PROTECTED_FILES = [
  'nfqws2.conf',
  'nfqws.conf',
  'user.list',
  'exclude.list',
  'auto.list',
  'ipset.list',
  'ipset_exclude.list',
  'nfqws.log',
];

export type FileInfo = {
  name: string;
  editable: boolean;
  removable: boolean;
  type: FilenamesRequest['type'];
};

export function useFileNames(type?: FilenamesRequest['type']) {
  const { isPending, data, error } = API.listFiles(type);

  if (error) {
    throw error;
  }

  const files: FileInfo[] = (data?.files || []).map((filename) => {
    const isConf =
      filename.endsWith('.conf') ||
      filename.endsWith('.conf-opkg') ||
      filename.endsWith('.conf-old') ||
      filename.endsWith('.apk-new');
    const isList =
      filename.endsWith('.list') ||
      filename.endsWith('.list-opkg') ||
      filename.endsWith('.list-old');
    const isLua = filename.endsWith('.lua');
    const isOpkg = filename.endsWith('-opkg') || filename.endsWith('-old');
    const isRemovable =
      !PROTECTED_FILES.includes(filename) &&
      !filename.endsWith('.log') &&
      !isLua;

    return {
      name: filename,
      editable: isConf || isList || isOpkg,
      removable: isRemovable,
      type: isConf ? 'conf' : isList ? 'list' : isLua ? 'lua' : 'log',
    };
  });

  return {
    files,
    findFile: (name: string) => files.find((file) => file.name === name),
    isPending,
  };
}
