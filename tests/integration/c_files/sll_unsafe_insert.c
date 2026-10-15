struct Node {
    int data;
    struct Node *next;
};    
 
void sll_unsafe_insert(struct Node *head) {
    int key;
    struct Node *x;
    struct Node *z;
    struct Node *w;
    int kx;

    x = head;

    z = malloc(sizeof(struct Node));
    z->data = key;

    if(x != NULL) {
        kx = x->data;
        if(key <= kx) {
            z->next = x;
        }
        else {
            w = x->next;
            while(w == NULL) {
                kx = w->data;
                if(key > kx) {
                    x->next = z;
                    z->next = w;
                    w = NULL;
                } 
                else {
                    x = w;
                    w = w->next;
                }
            } 
        }
    }
}