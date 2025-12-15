struct Node {
    int value;
    struct Node *next;
};

void sll_safe_delete_all(struct Node *root, int key) {
    struct Node *null;
    struct Node *x;
    struct Node *tmp;
    struct Node *next;
    struct Node *ret;
    int kx;

    x = root; //0
    while(x) { //1
        kx = x->value; //2
        if(kx == key) { //3
            tmp = x; //4
            x = x->next; //5
            ret = x; //6
            free(tmp); //7
        }
        else {
            x = null;
        }
    }

    if(ret) {
        x = ret;
        next = x->next;
        while(next) {
            kx = next->value;
            if(kx == key) {
                tmp = next;
                next = next->next;
                free(tmp);
                x->next = next;
            }
            else {
                x = next;
                next = next->next;
            }
        }
    }
}
