import CurrencyBitcoinIcon from '@mui/icons-material/CurrencyBitcoin';
import { SvgIcon } from '@mui/material';

type Asset = 'YOOMONEY' | 'TRON' | 'ETH' | 'SOL' | 'BTC';

export function SupportAssetIcon({ asset }: { asset: Asset }) {
  if (asset === 'BTC') {
    return <CurrencyBitcoinIcon sx={{ color: '#f7931a', fontSize: 28 }} />;
  }
  return (
    <SvgIcon viewBox="0 0 32 32" sx={{ fontSize: 28 }} aria-hidden="true">
      {asset === 'YOOMONEY' && (
        <>
          <circle cx="16" cy="16" r="15" fill="#8b3ffd" />
          <circle
            cx="11"
            cy="16"
            r="5"
            fill="none"
            stroke="white"
            strokeWidth="3.6"
          />
          <path d="M19 9h7v14h-7z" fill="white" />
        </>
      )}
      {asset === 'TRON' && (
        <path
          d="m5 3 22 5-12 22zM5 3l13 11 9-6M18 14l-3 16M5 3l10 27"
          fill="none"
          stroke="#ff5964"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      )}
      {asset === 'ETH' && (
        <>
          <path d="m16 1 10 15-10 6L6 16z" fill="#8b9bd5" />
          <path d="m16 1 10 15-10-5z" fill="#6276bc" />
          <path d="m16 23 10-6-10 14L6 17z" fill="#6276bc" />
          <path d="m16 23 10-6-10 14z" fill="#9aabe2" />
        </>
      )}
      {asset === 'SOL' && (
        <>
          <circle cx="16" cy="16" r="15" fill="#182027" />
          <path d="m9 7-4 4h18l4-4zM9 21l-4 4h18l4-4z" fill="#70e8c1" />
          <path d="m5 14 4 4h18l-4-4z" fill="#b493ff" />
        </>
      )}
    </SvgIcon>
  );
}
