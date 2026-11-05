<?php
require_once __DIR__.'/dpi-install.php';
require_once __DIR__.'/dpi-saved-store.php';
require_once __DIR__.'/dpi-store.php';
require_once __DIR__.'/dpi-terminal-lifecycle.php';

/** Called under the panel update lease after the owned terminal has stopped. */
final class AsusDpiRemoval
{
    public function __construct(private ?AsusDpiInstaller $installer=null,private ?AsusDpiSavedStore $saved=null,private ?AsusDpiStore $store=null,private ?AsusDpiTerminalLifecycle $gate=null){}
    public function remove(bool $reports): array
    {
        $store=$this->store??new AsusDpiStore();
        return $store->mutation(function()use($reports,$store){
        return ($this->gate??new AsusDpiTerminalLifecycle())->idle(function()use($reports,$store){
        if($store->status()['active']!==null)throw new RuntimeException('busy');
        $installer=$this->installer??new AsusDpiInstaller();
        if($reports){
            $saved=$this->saved??new AsusDpiSavedStore();
            try{
                $listing=$saved->refresh();
                if($listing['skipped']||$listing['scan_truncated']||!in_array($listing['code'],['ready','source_unavailable'],true))throw new RuntimeException('reports_not_removed');
                $pending=$listing['reports'];
                // A filename can have several reviewed snapshots. Remove the
                // snapshot matching its current source first, then old copies.
                while($pending){
                    $remaining=[];$progress=false;
                    foreach($pending as $report){
                        try{$saved->delete($report['id']);$progress=true;}
                        catch(Throwable $e){if($e->getMessage()!=='source_changed')throw $e;$remaining[]=$report;}
                    }
                    if(!$progress)throw new RuntimeException('reports_not_removed');
                    $pending=$remaining;
                }
                foreach($store->status()['history'] as $job)$store->deleteResult($job['id']);
            }catch(Throwable $e){throw new RuntimeException('reports_not_removed');}
        }
        $installer->uninstall();
        return ['removed'=>true,'reports_removed'=>$reports];
        });
        });
    }
}
