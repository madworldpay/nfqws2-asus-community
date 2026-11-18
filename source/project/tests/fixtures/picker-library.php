<?php
/** Make a real job-local profile with the included and excluded hosts for synthesis. */
function pickerFixtureProfile(NfqwsStrategyPickerState $store,bool $stock=false):array
{
    $config=dirname($store->root).'/profile-config';
    foreach(['','/lists','/lua','/blobs','/strategy-picker']as $suffix){
        $directory=$config.$suffix;
        if(!is_dir($directory)&&!mkdir($directory,0700))throw new RuntimeException('fixture_directory_failed');
    }
    $raw="NFQWS_ARGS=\"--filter-tcp=80\"\nNFQWS_EXTRA_ARGS=\"--hostlist=/opt/etc/nfqws2/lists/user.list --hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list\"\nTCP_PORTS=\"80\"\nUDP_PORTS=\"443\"\n";
    file_put_contents($config.'/nfqws2.conf',$raw);
    file_put_contents($config.'/lists/user.list',"video.example\n");
    file_put_contents($config.'/lists/exclude.list',"excluded.example\n");
    $library=$store->profileLibrary($store->read());
    if($stock)return $library->stock($raw);
    $saved=$library->capture('Measured fixture');
    return $library->entry($saved['id']);
}
