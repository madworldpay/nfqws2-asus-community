<?php
// Run as root or under fakeroot with the native PHP CLI.
declare(strict_types=1);
require_once dirname(__DIR__).'/webui/web/public/share-resources.php';
require_once dirname(__DIR__).'/webui/web/public/import-store.php';

function expect(bool $condition, string $message): void
{
    if (!$condition) throw new RuntimeException($message);
}

umask(0022);
$root = sys_get_temp_dir().'/keenetic-resources-'.bin2hex(random_bytes(6));
mkdir($root, 0700);
$opt = "$root/opt";
$base = "$opt/etc/nfqws2";
$source = "$opt/share/nfqws2-asus";
$state = "$opt/etc/nfqws-asus-web";
$installer = dirname(__DIR__).'/keenetic/resource-layout.php';
$run = static function(bool $expectRefusal=false) use ($installer, $root): int {
    putenv("IPKG_INSTROOT=$root");
    $process = proc_open([PHP_BINARY, '-n', $installer], [1=>['pipe','w'], 2=>['pipe','w']], $pipes);
    $output = stream_get_contents($pipes[1]).stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]);
    $rc = proc_close($process);
    if ($rc && (!$expectRefusal || !str_contains($output, 'Cannot prepare panel resources'))) throw new RuntimeException($output);
    return $rc;
};
try {
    foreach ([$base, $state, "$source/factory/lua"] as $dir) mkdir($dir, 0755, true);
    foreach (['lua','blobs','lists'] as $name) {
        mkdir("$base/$name",0755); chown("$base/$name",1001); chgrp("$base/$name",1001);
    }
    foreach (['user','exclude','auto'] as $name) {
        $file = "$base/lists/$name.list";
        file_put_contents($file, "$name.example.org\n"); chmod($file,0666);
        chown($file,$name==='auto'?65534:1001); chgrp($file,1001);
        clearstatcache(true,$file);
        $before[$name] = lstat($file);
    }
    $pins = [];
    foreach (['zapret-lib','zapret-antidpi','zapret-auto','local-tls13-stun','local-guarded-ts'] as $name) {
        $bytes = "-- packaged $name\n";
        file_put_contents("$source/factory/lua/$name.lua", $bytes);
        $pins["lua/$name.lua"] = ['sha256'=>hash('sha256',$bytes),'bytes'=>strlen($bytes)];
    }
    file_put_contents("$source/report-baseline.json", json_encode(['resources'=>$pins]));
    file_put_contents("$base/lua/local-tls13-stun.lua", "-- operator copy\n");
    copy("$source/factory/lua/local-guarded-ts.lua","$base/lua/local-guarded-ts.lua");
    chmod("$base/lua/local-guarded-ts.lua",0777);
    $reader = new AsusShareRead(0,$opt,$opt,true);
    $resources = new AsusShareResources($base,0,$pins,$reader);
    expect($resources->inventory()['files']===[], 'Legacy stock should reproduce the empty inventory');
    rename("$base/lists/user.list","$base/lists/user.original");
    symlink('user.original',"$base/lists/user.list");
    expect($run(true)!==0 && fileowner("$base/lua")===1001, 'Linked input changed the install tree');
    unlink("$base/lists/user.list"); rename("$base/lists/user.original","$base/lists/user.list");
    expect($run()===0 && $run()===0, 'First install or repeated upgrade failed');
    clearstatcache();
    foreach (['user','exclude','auto'] as $name) {
        $file = "$base/lists/$name.list"; $after = lstat($file);
        expect($after['uid']===($name==='auto'?65534:0), 'List owner mismatch');
        foreach (['dev','ino','gid','mode','nlink','size','mtime'] as $k)
            expect($before[$name][$k]===$after[$k], "$name $k changed");
        expect(file_get_contents($file)==="$name.example.org\n", 'List bytes changed');
        if ($name==='auto') expect($before[$name]['ctime']===$after['ctime'],'Learned list touched');
    }
    expect(count(glob("$state/resource-owners-*.json"))===1,'Unexpected duplicate backup');
    $backup = json_decode(file_get_contents(glob("$state/resource-owners-*.json")[0]),true,flags:JSON_THROW_ON_ERROR);
    expect(count($backup)===5 && base64_decode($backup['lists/user.list']['data_base64'],true)==="user.example.org\n",'Incomplete backup');
    expect(file_get_contents("$base/lua/local-tls13-stun.lua")==="-- operator copy\n",'Custom Lua overwritten');
    $files = array_column($resources->inventory()['files'],null,'name');
    foreach ($pins as $key=>$pin) {
        $row=$files['imported/'.$pin['sha256'].'.lua']??[];
        expect(($row['bundled_name']??'')===basename($key) && $row['bundled_lua']===true,'Missing verified package copy');
    }
    expect($files['local-guarded-ts.lua']['bundled_lua']===false,'Writable Lua trusted');
    chown("$base/lists/auto.list",1001);
    $fresh = new AsusShareRead(0,$opt,$opt,true,true);
    expect($fresh->bytes("$base/lists/auto.list",262144)==="auto.example.org\n" && $reader->stat("$base/lists/auto.list")===null,'Fresh vendor auto.list');
    file_put_contents("$base/lua/custom.lua",'-- private'); chown("$base/lua/custom.lua",1001); chgrp("$base/lua/custom.lua",1001);
    expect($fresh->stat("$base/lua/custom.lua")===null,'Vendor UID accepted outside the learning file');
    $legacy="$opt/var/lib/nfqws2-asus/import"; $private="$state/import";
    mkdir(dirname($legacy),0755,true);
    expect(AsusImportStore::keeneticRoot($opt)===$legacy,'Normal journal changed');
    chown("$opt/var",1001); chgrp("$opt/var",1001);
    expect(!$reader->directory(dirname($legacy)) && AsusImportStore::keeneticRoot($opt)===$private
        && $reader->directory(dirname($private)),'Vendor journal parent');
    mkdir($legacy,0700);
    expect(AsusImportStore::keeneticRoot($opt)===$legacy,'Existing journal ignored');
    mkdir($private,0700);
    try { AsusImportStore::keeneticRoot($opt); throw new LogicException('Two journals accepted'); }
    catch (RuntimeException $e) { expect($e->getMessage()==='restore_required','Unexpected journal selection'); }
    rmdir($legacy);chown("$opt/var",0);
    expect(AsusImportStore::keeneticRoot($opt)===$private,'Previously selected journal changed');
    echo "Legacy stock import layout, backup, retry and five package identities verified\n";
} finally {
    $entries = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,FilesystemIterator::SKIP_DOTS),RecursiveIteratorIterator::CHILD_FIRST);
    foreach ($entries as $entry) { if ($entry->isDir()&&!$entry->isLink()) rmdir($entry->getPathname()); else unlink($entry->getPathname()); }
    rmdir($root);
}
