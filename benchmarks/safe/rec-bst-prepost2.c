#include <stdlib.h>
#include<stdbool.h>

enum ReturnPC {
    B2, B3, RET
};

struct Node {
	int value;
	struct Node* left;
	struct Node* right;
	struct Node* parent;
	int minl;
	int maxl;
	int isbstl; //bool
	int minr;
	int maxr;
    int isbstr; //bool
	int retpc; // ReturnPC
	int min;
	int max;
	int isbst; //bool
};

void isBST(struct Node* root) {
	struct Node* current;
	struct Node* tmp;
	int return_min;
	int return_max;
	int return_isbst; //bool
	int value_tmp;
	int tmp_retpc; // ReturnPC
	int current_isbst; //bool
	current = root;
	if(!root) {
		return_isbst = 1; //true
        return_min = 0;
        return_max = 0;
	}
	else {
		root->parent = tmp; //tmp is null
		START:
		//begin <blocco1-new>
		current->isbst = 1; //true
		//end <blocco1-new>
		tmp = current->left;
		if(!tmp) {
    		return_isbst = 1; //true
            return_min = 0;
            return_max = 0;
            current->retpc = 2; // B2
            goto MyReturn;
		}
		tmp = current;
		current->retpc = 2; // B2
		current = current->left;
		current->parent = tmp;
		goto START;

		B2:
		current->isbstl = return_isbst;
		current->minl = return_min;
        current->maxl = return_max;
		//begin <blocco2-new>
		tmp = current->left;
		if(tmp) {
            current->min = return_min;
            current_isbst = current->isbst;
            value_tmp = current->value;
            if(current_isbst == 1 && return_isbst == 1 && value_tmp >= return_max) {
                current->isbst = 1; //true
            }
            else {
                current->isbst = 0; //false
            }
       	}
       	else {
            value_tmp = current->value;
      		current->min = value_tmp;
       	}
       	//end <blocco2-new>
        tmp = current->right;
        if(!tmp) {
      		return_isbst = 1; //true
            return_min = 0;
            return_max = 0;
            current->retpc = 3; // B3
            goto MyReturn;
        }
        tmp = current;
        current->retpc = 3; // B3
        current = current->right;
        current->parent = tmp;
        goto START;

        B3:
        current->isbstr = return_isbst;
        current->minr = return_min;
        current->maxr = return_max;
        //begin <blocco3-new>
        tmp = current->right;
        if(tmp) {
            current->max = return_max;
            current_isbst = current->isbst;
            value_tmp = current->value;
            if( current_isbst == 1 && return_isbst == 1 && value_tmp <= return_min) {
                current->isbst = 1; //true
            }
            else {
                current->isbst = 0; //false
            }
       	}
       	else {
            value_tmp = current->value;
      		current->max = value_tmp;
       	}
       	return_isbst = current->isbst;
       	return_min = current->min;
       	return_max = current->max;
       	current->retpc = 4; // RET
        goto MyReturn;

       	MyReturn:
        tmp_retpc = current->retpc;
        tmp = current->parent;
       	if(!tmp && tmp_retpc == 4) return; // tmp_retpc == RET
        if(tmp_retpc == 2) { // tmp_retpc == B2;
            goto B2;
        }
        else if(tmp_retpc == 3) { // tmp_retpc == B3
            goto B3;
        }
        else if(tmp_retpc == 4) { // tmp_retpc == RET
           	current = tmp;
            goto MyReturn;
        }
    }
}
