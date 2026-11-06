/* Domain matching is the unmodified pinned upstream hostlist.c + pools.c.
 * Kernel/logging/compressed-file boundaries are unused by this offline probe. */
#include "hostlist.h"
#include "gzip.h"
#include <string.h>
#include <stdlib.h>
struct params_s params;
int DLOG(const char *format, ...) { return 0; }
int DLOG_ERR(const char *format, ...) { return 0; }
int DLOG_PERROR(const char *s) { return 0; }
int DLOG_CONDUP(const char *format, ...) { return 0; }
bool file_mod_signature(const char *filename, file_mod_sig *ms) { return false; }
bool file_size(const char *filename, off_t *size) { return false; }
bool file_open_test(const char *filename, int flags) { return false; }
char *fgets_safe(char *s, int size, FILE *stream) { return fgets(s, size, stream); }
int z_readfile(FILE *f, char **buf, size_t *size, size_t extra) { return -1; }
bool is_gzip(FILE *f) { return false; }
static void domains(struct hostlist_file *file, char *value)
{
    for(char *item=strtok(value,",");item;item=strtok(NULL,","))
        if(!AppendHostlistItem(&file->hostlist,item))exit(3);
}
int main(int argc,char **argv)
{
    if(argc<2)return 2;
    struct desync_profile profiles[32]={0};
    struct hostlist_file *fixed[32]={0},*excluded[32]={0};
    unsigned n=0;
    for(int i=2;i<argc;i++){
        char *value=strchr(argv[i],'=');if(value)value++;
        if(!strcmp(argv[i],"--new")||!strncmp(argv[i],"--new=",6)){if(++n>=32)return 2;continue;}
        if(!strncmp(argv[i],"--hostlist-domains=",19)){
            if(!fixed[n])fixed[n]=RegisterHostlist(&profiles[n],false,NULL,false);
            domains(fixed[n],value);
        }else if(!strncmp(argv[i],"--hostlist-exclude-domains=",27)){
            if(!excluded[n])excluded[n]=RegisterHostlist(&profiles[n],true,NULL,false);
            domains(excluded[n],value);
        }else if(!strncmp(argv[i],"--hostlist=",11)||!strncmp(argv[i],"--hostlist-auto=",16)){
            struct hostlist_file *file=RegisterHostlist(&profiles[n],false,NULL,false);
            if(!AppendHostList(&file->hostlist,value))return 3;
            if(!strncmp(argv[i],"--hostlist-auto=",16))NonEmptyHostlist(&file->hostlist);
        }
    }
    for(unsigned i=0;i<=n;i++){
        bool excluded=false;
        printf("%u:%d:%d\n",i,HostlistCheck(&profiles[i],argv[1],false,&excluded,true),excluded);
    }
    return 0;
}
