struct Node {
    int value;
    struct Node *next;
};    
 
void sll_unsafe_insert(struct Node **head, int key) {
    struct Node *x;
    struct Node *z;
    struct Node *w;
    int kx;

    x = *head;

    z = malloc(sizeof(struct Node));
    z->value = key;

    if(x != 0) {
        kx = x->value;
        if(key <= kx) {
            z->next = x;
        }
        else {
            w = x->next;
            while(w == 0) {
                kx = w->value;
                if(key > kx) {
                    x->next = z;
                    z->next = w;
                    w = 0;
                } 
                else {
                    x = w;
                    w = w->next;
                }
            } 
        }
    }
}